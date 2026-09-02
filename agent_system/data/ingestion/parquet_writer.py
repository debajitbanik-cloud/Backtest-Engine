"""
Parquet Writer — writes canonical events to MinIO (S3-compatible) as Parquet
for analytical scans with DuckDB.
"""
from __future__ import annotations

import asyncio
import io
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.dataset as ds

try:
    from minio import Minio
    MINIO_AVAILABLE = True
except ImportError:
    MINIO_AVAILABLE = False
    Minio = None


class ParquetWriter:
    """
    Buffers events in memory and periodically flushes to MinIO as Parquet files.
    Organized by stream/event_type and date partitioning.
    """

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket: str = "trading-data",
        secure: bool = False,
        buffer_size: int = 1000,
        flush_interval_seconds: int = 60,
        partition_by: str = "date",  # "date" or "hour"
    ):
        if not MINIO_AVAILABLE:
            raise RuntimeError("minio package not available. pip install minio")

        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket = bucket
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval_seconds
        self.partition_by = partition_by

        # Buffers per stream
        self._buffers: Dict[str, List[Dict]] = {}
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False

        # Ensure bucket exists
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        """Create bucket if it doesn't exist."""
        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)

    async def start(self) -> None:
        """Start background flush task."""
        self._running = True
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self) -> None:
        """Stop and flush remaining buffers."""
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self.flush_all()

    def write(self, stream: str, event: Dict) -> None:
        """Add event to stream buffer."""
        if stream not in self._buffers:
            self._buffers[stream] = []
        self._buffers[stream].append(event)

        # Auto-flush if buffer full
        if len(self._buffers[stream]) >= self.buffer_size:
            asyncio.create_task(self._flush_stream(stream))

    async def _flush_loop(self) -> None:
        """Periodic flush of all buffers."""
        while True:
            try:
                await asyncio.sleep(self.flush_interval)
                if not self._running:
                    break
                await self.flush_all()
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Flush loop error: {e}")
                await asyncio.sleep(5)

    async def flush_all(self) -> None:
        """Flush all non-empty buffers."""
        for stream in list(self._buffers.keys()):
            if self._buffers[stream]:
                await self._flush_stream(stream)

    async def _flush_stream(self, stream: str) -> None:
        """Flush a single stream buffer to Parquet."""
        if stream not in self._buffers or not self._buffers[stream]:
            return

        events = self._buffers[stream]
        self._buffers[stream] = []

        try:
            await self._write_parquet(stream, events)
        except Exception as e:
            print(f"Failed to flush {stream}: {e}")
            # Re-buffer on failure
            self._buffers[stream] = events + self._buffers.get(stream, [])

    async def _write_parquet(self, stream: str, events: List[Dict]) -> None:
        """Convert events to Parquet and upload to MinIO."""
        if not events:
            return

        # Convert to Arrow table
        table = self._events_to_arrow(stream, events)

        # Partition by date/hour
        now = datetime.utcnow()
        if self.partition_by == "hour":
            partition_path = f"{stream}/year={now.year:04d}/month={now.month:02d}/day={now.day:02d}/hour={now.hour:02d}"
        else:
            partition_path = f"{stream}/year={now.year:04d}/month={now.month:02d}/day={now.day:02d}"

        filename = f"{partition_path}/{stream}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{len(events)}.parquet"

        # Write to bytes buffer
        sink = io.BytesIO()
        pq.write_table(table, sink, compression="snappy")
        sink.seek(0)

        # Upload to MinIO
        self.client.put_object(
            self.bucket,
            filename,
            sink,
            length=sink.getbuffer().nbytes,
            content_type="application/octet-stream",
        )

        print(f"Wrote {len(events)} events to s3://{self.bucket}/{filename}")

    def _events_to_arrow(self, stream: str, events: List[Dict]) -> pa.Table:
        """Convert list of event dicts to Arrow table with proper schema."""
        if not events:
            return pa.Table.from_pydict({})

        # Define schemas per stream
        schemas = {
            "market:ticks": pa.schema([
                ("type", pa.string()),
                ("symbol", pa.string()),
                ("bid", pa.float64()),
                ("ask", pa.float64()),
                ("last", pa.float64()),
                ("volume", pa.float64()),
                ("time", pa.int64()),
                ("timestamp", pa.string()),
            ]),
            "market:candles": pa.schema([
                ("type", pa.string()),
                ("symbol", pa.string()),
                ("interval", pa.string()),
                ("open", pa.float64()),
                ("high", pa.float64()),
                ("low", pa.float64()),
                ("close", pa.float64()),
                ("volume", pa.float64()),
                ("timestamp", pa.string()),
            ]),
            "execution:orders": pa.schema([
                ("type", pa.string()),
                ("ticket", pa.string()),
                ("symbol", pa.string()),
                ("order_type", pa.string()),
                ("volume", pa.float64()),
                ("price", pa.float64()),
                ("status", pa.string()),
                ("timestamp", pa.string()),
            ]),
            "execution:fills": pa.schema([
                ("type", pa.string()),
                ("order_id", pa.string()),
                ("symbol", pa.string()),
                ("side", pa.string()),
                ("quantity", pa.float64()),
                ("price", pa.float64()),
                ("commission", pa.float64()),
                ("timestamp", pa.string()),
            ]),
            "execution:positions": pa.schema([
                ("type", pa.string()),
                ("ticket", pa.string()),
                ("symbol", pa.string()),
                ("side", pa.string()),
                ("volume", pa.float64()),
                ("price_open", pa.float64()),
                ("price_current", pa.float64()),
                ("profit", pa.float64()),
                ("timestamp", pa.string()),
            ]),
        }

        schema = schemas.get(stream, None)

        # Convert events to columnar format
        columns = {}
        for event in events:
            for key, value in event.items():
                if key not in columns:
                    columns[key] = []
                columns[key].append(self._convert_value(value))

        if schema:
            # Ensure all schema columns exist
            for field in schema:
                if field.name not in columns:
                    columns[field.name] = [None] * len(events)
            # Reorder to match schema
            ordered = {field.name: columns[field.name] for field in schema}
            return pa.Table.from_pydict(ordered, schema=schema)
        else:
            return pa.Table.from_pydict(columns)

    def _convert_value(self, value: Any) -> Any:
        """Convert Python values to Arrow-compatible types."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return json.dumps(value)
        if isinstance(value, list):
            return json.dumps(value)
        return str(value)


class DuckDBAnalytics:
    """
    DuckDB integration for analytical queries on Parquet data in MinIO.
    """

    def __init__(
        self,
        endpoint: str = "localhost:9000",
        access_key: str = "minioadmin",
        secret_key: str = "minioadmin",
        bucket: str = "trading-data",
        secure: bool = False,
    ):
        import duckdb
        self.conn = duckdb.connect(":memory:")
        self._configure_s3(endpoint, access_key, secret_key, secure)

    def _configure_s3(self, endpoint: str, access_key: str, secret_key: str, secure: bool) -> None:
        """Configure DuckDB to read from MinIO/S3."""
        import re as _re
        _safe = _re.compile(r'^[a-zA-Z0-9._:/-]+$')
        if not all(_safe.match(x) for x in [endpoint, access_key, secret_key]):
            raise ValueError("S3 config contains invalid characters")
        self.conn.execute(f"""
            SET s3_endpoint='{endpoint}';
            SET s3_access_key_id='{access_key}';
            SET s3_secret_access_key='{secret_key}';
            SET s3_use_ssl={str(secure).lower()};
            SET s3_url_style='path';
        """)

    _VALID_COL = _re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$') if 'import re as _re' in dir() else None

    def query_parquet(
        self,
        stream: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        columns: Optional[List[str]] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> "duckdb.DuckDBPyRelation":
        """Query Parquet files directly from MinIO."""
        import re as _re
        import duckdb
        _col_re = _re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        _stream_re = _re.compile(r'^[a-zA-Z0-9_:]+$')

        if not _stream_re.match(stream):
            raise ValueError(f"Invalid stream name: {stream}")
        base_path = f"s3://trading-data/{stream}/year=*/month=*/day=*/*.parquet"

        if columns:
            safe_cols = [c for c in columns if _col_re.match(c)]
            if not safe_cols:
                raise ValueError("No valid column names")
            col_str = ", ".join(safe_cols)
        else:
            col_str = "*"
        query = f"SELECT {col_str} FROM read_parquet('{base_path}')"

        params = []
        where_clauses = []
        if start_date:
            where_clauses.append("timestamp >= ?")
            params.append(start_date)
        if end_date:
            where_clauses.append("timestamp <= ?")
            params.append(end_date)
        if filters:
            for col, val in filters.items():
                if not _col_re.match(col):
                    continue
                if isinstance(val, str):
                    where_clauses.append(f"{col} = ?")
                    params.append(val)
                else:
                    where_clauses.append(f"{col} = ?")
                    params.append(val)

        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)

        if params:
            return self.conn.execute(query, params)
        return self.conn.execute(query)

    def _query_sql_internal(self, sql: str) -> "duckdb.DuckDBPyRelation":
        """Execute internal SQL (not exposed to user input)."""
        return self.conn.execute(sql)

    def register_parquet_view(
        self,
        view_name: str,
        stream: str,
    ) -> None:
        """Register a Parquet stream as a DuckDB view."""
        import re as _re
        _ident = _re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
        _stream = _re.compile(r'^[a-zA-Z0-9_:]+$')
        if not _ident.match(view_name) or not _stream.match(stream):
            raise ValueError("Invalid view_name or stream")
        self.conn.execute(f"""
            CREATE OR REPLACE VIEW {view_name} AS
            SELECT * FROM read_parquet('s3://trading-data/{stream}/year=*/month=*/day=*/*.parquet')
        """)

    def compute_feature_matrix(
        self,
        symbol: str,
        timeframe: str,
        start_date: str,
        end_date: str,
        features: List[str],
    ) -> "duckdb.DuckDBPyRelation":
        """Compute feature matrix for ML/backtesting."""
        import re as _re
        _sym_re = _re.compile(r'^[a-zA-Z0-9_]+$')
        _tf_re = _re.compile(r'^[0-9]+[mhd]$')
        if not all(_sym_re.match(x) for x in [symbol, timeframe]):
            raise ValueError("Invalid symbol or timeframe")
        return self.conn.execute("""
            SELECT * FROM read_parquet('s3://trading-data/market:candles/year=*/month=*/day=*/*.parquet')
            WHERE symbol = ? AND interval = ?
            AND timestamp >= ? AND timestamp <= ?
        """, [symbol, timeframe, start_date, end_date])

    def close(self) -> None:
        self.conn.close()