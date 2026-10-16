# Standard Library
import asyncio
import json
import logging
import socket

from net import lan_ip
import threading
from pathlib import Path

# Third Party Library
from aiohttp import web, WSMsgType
from zeroconf import ServiceInfo, Zeroconf

log = logging.getLogger('beambar.phone')

PAD_HTML = Path(__file__).with_name('pad.html')
PORT = 8788
from paths import PHONE_HOSTNAME as HOSTNAME
PHONE_HEAD = '''<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="BeamBar">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="apple-touch-icon" href="/icon.png">
<script>window.__phone = true;</script>
<style>
  html, body { background: #0b0d18 !important; min-height: 100%; }
  body { width: 100% !important; max-width: 420px; margin: 0 auto !important; padding: env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .remote { border-radius: 0 !important; min-height: 100vh; padding-top: max(34px, env(safe-area-inset-top)) !important; }
  .close, .minimize { display: none !important; }
  .surface { height: 40vh !important; min-height: 220px; }
  .palette { top: 54px; }
</style>
'''
PHONE_SCRIPT = '''<script>
(() => {
  const url = (location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws';
  let ws = null, timer = null;
  const queue = [];
  function connect() {
    ws = new WebSocket(url);
    ws.onopen = () => { while (queue.length) ws.send(queue.shift()); };
    ws.onmessage = (e) => { const m = JSON.parse(e.data); if (!window.remote) return; if (m.status) window.remote.setStatus(m.status); if (m.search) window.remote.setSearchResults(m.search); if (m.toast) window.remote.toast(m.toast); };
    ws.onclose = () => { clearTimeout(timer); timer = setTimeout(connect, 1500); };
  }
  window.__phoneSend = (msg) => { const s = JSON.stringify(msg); if (ws && ws.readyState === 1) ws.send(s); else queue.push(s); };
  connect();
  document.addEventListener('gesturestart', (e) => e.preventDefault());
})();
</script>'''
MANIFEST = {
    'name': 'BeamBar Remote',
    'short_name': 'BeamBar',
    'display': 'standalone',
    'background_color': '#0d0d10',
    'theme_color': '#0d0d10',
    'start_url': '/',
    'icons': [{'src': '/icon.png', 'sizes': '512x512', 'type': 'image/png'}],
}
ICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><rect width="512" height="512" rx="112" fill="#1c1c1f"/>
<rect x="96" y="128" width="320" height="200" rx="40" fill="#2c2c30"/><circle cx="256" cy="228" r="48" fill="#f2f2f2"/>
<rect x="156" y="372" width="200" height="36" rx="18" fill="#3a3a3f"/></svg>'''



class PhoneServer:
    def __init__(self, on_message, status_provider, port=PORT):
        self.on_message = on_message
        self.status_provider = status_provider
        self.port = port
        self.clients = set()
        self.loop = None
        self.zeroconf = None
        self.info = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        app = web.Application()
        app.router.add_get('/', self.index)
        app.router.add_get('/ws', self.websocket)
        app.router.add_get('/manifest.webmanifest', lambda r: web.json_response(MANIFEST))
        app.router.add_get('/icon.png', self.icon)
        app.router.add_get('/icon.svg', lambda r: web.Response(text=ICON_SVG, content_type='image/svg+xml'))
        runner = web.AppRunner(app, access_log=None)
        self.loop.run_until_complete(runner.setup())
        site = web.TCPSite(runner, '0.0.0.0', self.port)
        self.loop.run_until_complete(site.start())
        self.advertise()
        log.info('phone remote at http://%s:%d and http://%s.local:%d', lan_ip(), self.port, HOSTNAME, self.port)
        self.loop.run_forever()

    def advertise(self):
        try:
            self.zeroconf = Zeroconf()
            self.info = ServiceInfo(
                '_http._tcp.local.',
                'BeamBar Remote._http._tcp.local.',
                addresses=[socket.inet_aton(lan_ip())],
                port=self.port,
                properties={'path': '/'},
                server=f'{HOSTNAME}.local.',
            )
            self.zeroconf.register_service(self.info)
        except Exception as exc:
            log.warning('mDNS advertise failed: %s', exc)

    async def index(self, request):
        html = PAD_HTML.read_text()
        html = html.replace('<title>BeamBar Remote</title>', '<title>BeamBar Remote</title>\n' + PHONE_HEAD, 1)
        html = html.replace('</body>', PHONE_SCRIPT + '\n</body>', 1)
        return web.Response(text=html, content_type='text/html')

    async def icon(self, request):
        drawn = Path(__file__).resolve().parent / 'assets' / 'icon-512.png'
        if drawn.exists():
            return web.Response(body=drawn.read_bytes(), content_type='image/png')

        # Third Party Library
        from AppKit import NSBitmapImageFileTypePNG, NSBitmapImageRep, NSData, NSImage

        data = NSData.dataWithBytes_length_(ICON_SVG.encode(), len(ICON_SVG.encode()))
        image = NSImage.alloc().initWithData_(data)
        image.setSize_((512, 512))
        image.lockFocus()
        rep = NSBitmapImageRep.alloc().initWithFocusedViewRect_(((0, 0), (512, 512)))
        image.unlockFocus()
        png = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
        return web.Response(body=bytes(png), content_type='image/png')

    async def websocket(self, request):
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        self.clients.add(ws)
        try:
            await ws.send_str(json.dumps({'status': self.status_provider()}))
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        self.on_message(json.loads(msg.data))
                    except Exception:
                        log.exception('phone message failed')
                elif msg.type == WSMsgType.ERROR:
                    break
        finally:
            self.clients.discard(ws)
        return ws

    def push_search(self, query, results):
        if self.loop is None or not self.clients:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(json.dumps({'search': {'query': query, 'results': results}})), self.loop)

    def push_status(self, status):
        if self.loop is None or not self.clients:
            return
        payload = json.dumps({'status': status})
        asyncio.run_coroutine_threadsafe(self._broadcast(payload), self.loop)

    def toast(self, text):
        """Shows a short message on every connected phone."""
        if self.loop is None or not self.clients:
            return
        asyncio.run_coroutine_threadsafe(self._broadcast(json.dumps({'toast': text})), self.loop)

    async def _broadcast(self, payload):
        for ws in list(self.clients):
            try:
                await ws.send_str(payload)
            except Exception:
                self.clients.discard(ws)

    def url(self):
        return f'http://{lan_ip()}:{self.port}'
