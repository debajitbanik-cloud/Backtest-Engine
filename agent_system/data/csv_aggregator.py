"""
CSV Tick-to-Candle Aggregator
Reads tick-level trade CSV files and aggregates them into OHLCV candles
at various timeframes for both TypeScript and Python engines.
"""
from __future__ import annotations
import csv
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Iterator
from collections import defaultdict
import pandas as pd
import numpy as np

from data.free_crypto_feed import CandleData


class TickToCandleAggregator:
    """
    Aggregates tick-level trade data into OHLCV candles.
    
    CSV format expected:
        product_symbol,price,size,timestamp,buyer_role
        SOLUSD,124.673,247.0,2026-01-01 00:00:08.437767,taker
    
    Output: JSON files matching the format used by both engines.
    """
    
    VALID_TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1d']
    TIMEFRAME_SECONDS = {
        '1m': 60, '3m': 180, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400, '1d': 86400
    }
    
    def __init__(self, data_dir: str = "./data/shared", 
                 output_dir: str = "./data/shared",
                 timeframes: List[str] = None):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.timeframes = timeframes or ['1m', '5m', '15m']
    
    def find_csv_files(self, symbol: str = None) -> List[Path]:
        """Find all CSV files, optionally filtered by symbol."""
        pattern = f"{symbol}*.csv" if symbol else "*.csv"
        return sorted(self.data_dir.glob(pattern))
    
    def read_ticks_from_csv(self, filepath: Path) -> Iterator[Dict]:
        """Read tick data from CSV file, yielding as dicts."""
        with open(filepath, 'r', newline='') as f:
            reader = csv.DictReader(f)
            for row in reader:
                yield {
                    'symbol': row.get('product_symbol', ''),
                    'price': float(row['price']),
                    'size': float(row['size']),
                    'timestamp': self._parse_timestamp(row['timestamp']),
                    'buyer_role': row.get('buyer_role', '')
                }
    
    def _parse_timestamp(self, ts: str) -> int:
        """Parse timestamp string to Unix milliseconds."""
        # Try common formats
        formats = [
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%d',
        ]
        
        for fmt in formats:
            try:
                dt = datetime.strptime(ts.strip(), fmt)
                return int(dt.timestamp() * 1000)
            except ValueError:
                continue
        
        # Fallback to pandas
        try:
            ts_val = pd.to_datetime(ts)
            return int(ts_val.timestamp() * 1000)
        except Exception:
            return 0
    
    def aggregate_ticks_to_candles(self, ticks: List[Dict], timeframe: str) -> List[CandleData]:
        """Aggregate tick data into candles at the specified timeframe."""
        if not ticks:
            return []
        
        tf_seconds = self.TIMEFRAME_SECONDS[timeframe]
        tf_ms = tf_seconds * 1000
        
        symbol = ticks[0]['symbol'].replace('USD', 'USDT') if 'USD' in ticks[0]['symbol'] else ticks[0]['symbol']
        
        # Group ticks by timeframe bucket
        buckets = defaultdict(list)
        for tick in ticks:
            bucket_start = (tick['timestamp'] // tf_ms) * tf_ms
            buckets[bucket_start].append(tick)
        
        # Build candles from buckets
        candles = []
        for bucket_start in sorted(buckets.keys()):
            bucket_ticks = buckets[bucket_start]
            
            prices = [t['price'] for t in bucket_ticks]
            volumes = [t['size'] for t in bucket_ticks]
            
            candle = CandleData(
                symbol=symbol,
                timeframe=timeframe,
                open=prices[0],
                high=max(prices),
                low=min(prices),
                close=prices[-1],
                volume=sum(volumes),
                timestamp=datetime.fromtimestamp(bucket_start / 1000),
                closed=True
            )
            candles.append(candle)
        
        return candles
    
    def process_symbol(self, symbol: str, timeframes: List[str] = None) -> Dict[str, int]:
        """Process all CSV files for a symbol and generate candles."""
        timeframes = timeframes or self.timeframes
        
        # Determine actual symbol format from CSV filename
        csv_files = self.find_csv_files(symbol.replace('USDT', '') if symbol.endswith('USDT') else symbol)
        if not csv_files:
            # Try broader search
            csv_files = self.find_csv_files()
            csv_files = [f for f in csv_files if symbol.replace('USDT', '').upper() in f.name.upper()]
        
        if not csv_files:
            print(f"No CSV files found for {symbol}")
            return {tf: 0 for tf in timeframes}
        
        print(f"Processing {len(csv_files)} files for {symbol}")
        
        # Read all ticks
        all_ticks = []
        for csv_file in csv_files:
            ticks = list(self.read_ticks_from_csv(csv_file))
            all_ticks.extend(ticks)
        
        print(f"Total ticks loaded: {len(all_ticks)}")
        
        results = {}
        
        for tf in timeframes:
            candles = self.aggregate_ticks_to_candles(all_ticks, tf)
            self._save_candles(candles, symbol, tf)
            results[tf] = len(candles)
            print(f"  {tf}: {len(candles)} candles saved")
        
        return results
    
    def process_all(self, timeframes: List[str] = None) -> Dict[str, Dict[str, int]]:
        """Process all CSV files in the data directory."""
        timeframes = timeframes or self.timeframes
        csv_files = self.find_csv_files()
        
        if not csv_files:
            print(f"No CSV files found in {self.data_dir}")
            return {}
        
        # Extract unique symbols from CSV filenames
        symbols = set()
        for f in csv_files:
            # Filename format: SYMBOL_YYYY-MM.csv
            name = f.stem  # e.g., SOLUSD_2026-01
            symbol = name.split('_')[0]  # e.g., SOLUSD
            symbols.add(symbol)
        
        all_results = {}
        for symbol in sorted(symbols):
            try:
                result = self.process_symbol(symbol, timeframes)
                all_results[symbol] = result
            except Exception as e:
                print(f"Error processing {symbol}: {e}")
        
        return all_results
    
    def _save_candles(self, candles: List[CandleData], symbol: str, timeframe: str) -> None:
        """Save candles to JSON file (compatible with TypeScript engine)."""
        # Normalize symbol for filename: SOLUSD -> SOLUSDT, BTCUSD -> BTCUSDT
        norm_symbol = symbol.replace('USD', 'USDT') if symbol.endswith('USD') else symbol
        filename = f"{norm_symbol}_{timeframe}.json"
        filepath = self.output_dir / filename
        
        data = []
        for c in candles:
            data.append({
                'symbol': c.symbol,
                'timeframe': c.timeframe,
                'open': c.open,
                'high': c.high,
                'low': c.low,
                'close': c.close,
                'volume': c.volume,
                'timestamp': c.timestamp.isoformat(),
                'closed': c.closed
            })
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
    
    def aggregate_into_existing(self, symbol: str, timeframe: str, 
                                 existing_candles: List[CandleData]) -> List[CandleData]:
        """Merge new aggregated candles with existing ones."""
        # This could be used for incremental updates
        pass


def main():
    parser = argparse.ArgumentParser(description='Aggregate CSV tick data into OHLCV candles')
    parser.add_argument('--symbol', type=str, default=None, help='Symbol to process (e.g., SOLUSD)')
    parser.add_argument('--timeframes', type=str, default='1m,5m,15m', 
                       help='Comma-separated timeframes')
    parser.add_argument('--data-dir', type=str, default='./data/shared')
    parser.add_argument('--output-dir', type=str, default='./data/shared')
    
    args = parser.parse_args()
    timeframes = args.timeframes.split(',')
    
    aggregator = TickToCandleAggregator(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        timeframes=timeframes
    )
    
    if args.symbol:
        result = aggregator.process_symbol(args.symbol, timeframes)
    else:
        result = aggregator.process_all(timeframes)
    
    print(f"\nAggregation complete: {result}")


if __name__ == '__main__':
    main()