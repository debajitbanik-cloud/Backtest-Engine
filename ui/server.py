"""
Static file server for the admin UI + single-origin reverse proxy to the
Python bridge. Serving API under the same origin means the UI can use
relative URLs, so one tunnel/host exposes the whole app (required for
Cloudflare Tunnel demos and the later VM deployment).
"""
import asyncio
import os
from pathlib import Path
import aiohttp
from aiohttp import web


BACKEND = os.environ.get('BRIDGE_URL', 'http://127.0.0.1:8088')
API_PREFIXES = (
    '/delta', '/journal', '/events', '/analytics', '/backtest', '/bot',
    '/calendar', '/strategies', '/market', '/metrics', '/trading',
    '/health', '/status', '/signals',
)
HOP_BY_HOP = {'host', 'content-length', 'transfer-encoding', 'connection'}


async def proxy_api(request: web.Request) -> web.StreamResponse:
    """Forward API calls (incl. the SSE stream) to the bridge."""
    qs = ('?' + request.query_string) if request.query_string else ''
    url = BACKEND + request.path + qs
    headers = {k: v for k, v in request.headers.items() if k.lower() not in HOP_BY_HOP}
    body = await request.read()
    sess = request.app['client']
    try:
        # No total timeout: the /events SSE stream is long-lived; the
        # 10s connect timeout still fails fast when the bridge is down.
        async with sess.request(request.method, url, headers=headers, data=body or None,
                                timeout=aiohttp.ClientTimeout(total=None, sock_connect=10)) as resp:
            out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in HOP_BY_HOP}
            out = web.StreamResponse(status=resp.status, headers=out_headers)
            await out.prepare(request)
            async for chunk in resp.content.iter_chunked(8192):
                await out.write(chunk)
            await out.write_eof()
            return out
    except (aiohttp.ClientConnectionError, asyncio.TimeoutError):
        return web.json_response({'error': 'bridge_unreachable',
                                  'message': f'Backend {BACKEND} is down'}, status=502)


async def serve_ui(request: web.Request) -> web.Response:
    """Serve UI files."""
    file_path = request.match_info.get('path', 'index.html')
    ui_dir = Path(__file__).parent
    target = (ui_dir / file_path).resolve()
    
    if not target.is_relative_to(ui_dir.resolve()) or not target.exists() or not target.is_file():
        target = ui_dir / 'index.html'
    
    content_type = 'text/html'
    if target.suffix == '.jsx':
        content_type = 'text/javascript'
    elif target.suffix == '.css':
        content_type = 'text/css'
    
    return web.FileResponse(target, headers={'Content-Type': content_type})


async def _make_client(app: web.Application):
    app['client'] = aiohttp.ClientSession()


async def _close_client(app: web.Application):
    await app['client'].close()


def create_ui_app() -> web.Application:
    """Create UI server app (proxy routes first, static catch-all last)."""
    app = web.Application()
    for p in API_PREFIXES:
        app.router.add_route('*', p, proxy_api)
        app.router.add_route('*', p + '/{tail:.*}', proxy_api)
    app.router.add_get('/', serve_ui)
    app.router.add_get('/{path:.*}', serve_ui)
    app.on_startup.append(_make_client)
    app.on_cleanup.append(_close_client)
    return app


async def start_ui_server(port: int = 3000):
    """Start UI server."""
    app = create_ui_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '127.0.0.1', port)
    await site.start()
    print(f"Admin UI running at http://127.0.0.1:{port}")
    return runner


if __name__ == '__main__':
    import asyncio
    asyncio.run(start_ui_server())
