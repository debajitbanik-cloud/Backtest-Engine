"""
Simple static file server for the admin UI.
"""
from pathlib import Path
from aiohttp import web


async def serve_ui(request: web.Request) -> web.Response:
    """Serve UI files."""
    file_path = request.match_info.get('path', 'index.html')
    ui_dir = Path(__file__).parent
    target = ui_dir / file_path
    
    if not target.exists() or not target.is_file():
        target = ui_dir / 'index.html'
    
    content_type = 'text/html'
    if target.suffix == '.jsx':
        content_type = 'text/javascript'
    elif target.suffix == '.css':
        content_type = 'text/css'
    
    return web.FileResponse(target, headers={'Content-Type': content_type})


def create_ui_app() -> web.Application:
    """Create UI server app."""
    app = web.Application()
    app.router.add_get('/', serve_ui)
    app.router.add_get('/{path:.*}', serve_ui)
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
