"""Tests for indicator endpoints + storage (Task 8).

RED-phase: these fail until bridge/python_bridge.py gains
POST /indicators/upload, GET /indicators, GET /indicators/{id}/series,
DELETE /indicators/{id} with Bearer auth.
"""
import sys
from pathlib import Path

import pytest
import pytest_asyncio

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from aiohttp import FormData
from aiohttp.test_utils import TestClient, TestServer

from bridge.python_bridge import PythonBridge, BridgeConfig, _AUTH_TOKEN

SMA_PINE = """//@version=5
indicator("SMA Test", overlay=true)
len = input.int(10, title="Period", minval=2, maxval=100)
sma_val = ta.sma(close, len)
plot(sma_val, title="SMA", color=color.blue)
"""

AUTH = {"Authorization": f"Bearer {_AUTH_TOKEN}"}


@pytest.fixture
def bridge_app(tmp_path):
    cfg = BridgeConfig()
    b = PythonBridge(cfg)
    # Isolate storage per-test (never touch real data/indicators/).
    b.indicators_dir = tmp_path / "indicators"
    b.indicators_dir.mkdir(parents=True, exist_ok=True)
    return b


@pytest_asyncio.fixture
async def client(bridge_app):
    c = TestClient(TestServer(bridge_app.app))
    await c.start_server()
    yield c
    await c.close()


async def _upload(c, text=SMA_PINE, filename="sma.pine", headers=AUTH):
    form = FormData()
    form.add_field("file", text.encode(), filename=filename,
                   content_type="text/plain")
    return await c.post("/indicators/upload", data=form, headers=headers)


class TestIndicatorEndpoints:
    @pytest.mark.asyncio
    async def test_upload_list_series_delete_roundtrip(self, client, bridge_app):
        # Fake OHLCV so series never hits the network.
        async def fake_fetch(asset, timeframe, limit):
            return [
                {"open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
                 "close": 100.5 + i, "volume": 1000}
                for i in range(60)
            ]

        bridge_app._fetch_ohlcv = fake_fetch

        # upload
        resp = await _upload(client)
        assert resp.status == 200, await resp.text()
        body = await resp.json()
        assert "id" in body and body["id"]
        assert "errors" in body
        ind_id = body["id"]

        # list
        resp = await client.get("/indicators", headers=AUTH)
        assert resp.status == 200
        lst = await resp.json()
        ids = [r["id"] for r in lst.get("indicators", lst.get("items", []))
               if isinstance(r, dict) and "id" in r] if isinstance(lst, dict) else []
        # accept either {"indicators": [...]} or plain list
        if isinstance(lst, list):
            ids = [r["id"] for r in lst]
        assert ind_id in ids

        # series
        resp = await client.get(
            f"/indicators/{ind_id}/series?symbol=BTCUSD&timeframe=1h",
            headers=AUTH)
        assert resp.status == 200, await resp.text()
        series = await resp.json()
        assert "plots" in series and len(series["plots"]) >= 1
        assert series["plots"][0]["values"]

        # series with valid input override
        resp = await client.get(
            f"/indicators/{ind_id}/series?symbol=BTCUSD&timeframe=1h&len=5",
            headers=AUTH)
        assert resp.status == 200, await resp.text()

        # delete
        resp = await client.delete(f"/indicators/{ind_id}", headers=AUTH)
        assert resp.status == 200, await resp.text()

        # list again — gone
        resp = await client.get("/indicators", headers=AUTH)
        body2 = await resp.json()
        items = body2.get("indicators", body2 if isinstance(body2, list) else [])
        assert all(r.get("id") != ind_id for r in items)

    @pytest.mark.asyncio
    async def test_upload_requires_auth(self, client):
        resp = await _upload(client, headers={})
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_list_requires_auth(self, client):
        resp = await client.get("/indicators")
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_upload_rejects_bad_extension(self, client):
        resp = await _upload(client, filename="evil.txt")
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_upload_rejects_oversize(self, client):
        big = "x" * (200 * 1024 + 1)
        resp = await _upload(client, text=big)
        assert resp.status in (400, 413)

    @pytest.mark.asyncio
    async def test_series_rejects_unknown_input(self, client, bridge_app):
        async def fake_fetch(asset, timeframe, limit):
            return [
                {"open": 100.0 + i, "high": 101.0 + i, "low": 99.0 + i,
                 "close": 100.5 + i, "volume": 1000}
                for i in range(60)
            ]

        bridge_app._fetch_ohlcv = fake_fetch
        resp = await _upload(client)
        assert resp.status == 200
        ind_id = (await resp.json())["id"]
        resp = await client.get(
            f"/indicators/{ind_id}/series?symbol=BTCUSD&timeframe=1h&nope=123",
            headers=AUTH)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_delete_unknown_id_404(self, client):
        resp = await client.delete("/indicators/doesnotexist123",
                                   headers=AUTH)
        assert resp.status == 404
