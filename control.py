# Standard Library
import json
import logging
import os
import socket
import threading
from pathlib import Path

log = logging.getLogger('beambar.control')

from paths import SOCKET_PATH


class ControlServer:
    """Unix-socket JSON-lines server so the CLI, Shortcuts and other tools can drive the app."""

    def __init__(self, handler):
        self.handler = handler
        self.server = None

    def start(self):
        SOCKET_PATH.parent.mkdir(parents=True, exist_ok=True)
        if SOCKET_PATH.exists():
            SOCKET_PATH.unlink()
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(SOCKET_PATH))
        os.chmod(SOCKET_PATH, 0o600)
        self.server.listen(8)
        threading.Thread(target=self.serve, daemon=True).start()
        log.info('control socket at %s', SOCKET_PATH)

    def serve(self):
        while True:
            try:
                conn, _ = self.server.accept()
            except OSError:
                return
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn):
        with conn, conn.makefile('rwb') as stream:
            for line in stream:
                try:
                    request = json.loads(line)
                    reply = self.handler(request)
                except Exception as exc:
                    log.exception('control request failed')
                    reply = {'ok': False, 'error': str(exc)}
                stream.write((json.dumps(reply) + '\n').encode())
                stream.flush()


def send(request, timeout=10):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(timeout)
    client.connect(str(SOCKET_PATH))
    with client, client.makefile('rwb') as stream:
        stream.write((json.dumps(request) + '\n').encode())
        stream.flush()
        line = stream.readline()
    return json.loads(line) if line else {'ok': False, 'error': 'no reply'}
