# Standard Library
import logging
import mimetypes
import os
import re

from net import lan_ip
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger('beambar.caster')

PORT = 8765
CHUNK = 256 * 1024
CONTENT_TYPES = {
    '.mp4': 'video/mp4',
    '.m4v': 'video/mp4',
    '.mov': 'video/mp4',
    '.webm': 'video/webm',
    '.mkv': 'video/x-matroska',
    '.mp3': 'audio/mpeg',
    '.m4a': 'audio/mp4',
    '.aac': 'audio/aac',
    '.wav': 'audio/wav',
    '.flac': 'audio/flac',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
}
PLAYABLE = ('.mp4', '.m4v', '.mov', '.webm', '.mp3', '.m4a', '.aac', '.wav', '.flac', '.jpg', '.jpeg', '.png')


def content_type_for(path):
    suffix = Path(path).suffix.lower()
    return CONTENT_TYPES.get(suffix) or mimetypes.guess_type(str(path))[0] or 'application/octet-stream'



class MediaServer:
    def __init__(self):
        self.files = {}
        self.server = None

    def start(self):
        if self.server is not None:
            return
        files = self.files

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                log.debug('media server: ' + fmt, *args)

            def do_HEAD(self):
                self._serve(head=True)

            def do_GET(self):
                self._serve(head=False)

            def _serve(self, head):
                path = files.get(self.path.split('?')[0])
                if path is None or not os.path.isfile(path):
                    self.send_error(404)
                    return
                size = os.path.getsize(path)
                start, end = 0, size - 1
                partial = False
                match = re.match(r'bytes=(\d*)-(\d*)', self.headers.get('Range', ''))
                if match:
                    partial = True
                    if match.group(1):
                        start = int(match.group(1))
                        if match.group(2):
                            end = min(int(match.group(2)), size - 1)
                    elif match.group(2):
                        start = max(size - int(match.group(2)), 0)
                    if start > end or start >= size:
                        self.send_response(416)
                        self.send_header('Content-Range', f'bytes */{size}')
                        self.end_headers()
                        return
                self.send_response(206 if partial else 200)
                self.send_header('Content-Type', content_type_for(path))
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Content-Length', str(end - start + 1))
                if partial:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.end_headers()
                if head:
                    return
                try:
                    with open(path, 'rb') as handle:
                        handle.seek(start)
                        remaining = end - start + 1
                        while remaining > 0:
                            data = handle.read(min(CHUNK, remaining))
                            if not data:
                                break
                            self.wfile.write(data)
                            remaining -= len(data)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        self.server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        log.info('media server listening on %s:%d', lan_ip(), PORT)

    def url_for(self, path):
        self.start()
        path = str(Path(path).expanduser().resolve())
        route = '/' + quote(Path(path).name)
        self.files[route] = path
        return f'http://{lan_ip()}:{PORT}{route}'


def play(cast, url, content_type=None, title=None):
    controller = cast.media_controller
    controller.play_media(url, content_type or content_type_for(url), title=title)
    controller.block_until_active(timeout=15)
    return controller.status.player_state
