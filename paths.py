# Standard Library
from pathlib import Path

_NEW = Path.home() / '.config' / 'beambar'
_LEGACY = Path.home() / '.config' / 'xgimi-bar'

# Setups from before the rename keep their folder, pairing keys, log and phone link.
LEGACY = _LEGACY.exists() and not _NEW.exists()

CONFIG_DIR = _LEGACY if LEGACY else _NEW
CONFIG_FILE = CONFIG_DIR / 'config.json'
CERT_FILE = CONFIG_DIR / 'cert.pem'
KEY_FILE = CONFIG_DIR / 'key.pem'
SOCKET_PATH = CONFIG_DIR / 'control.sock'
LOG_FILE = Path.home() / 'Library' / 'Logs' / ('xgimi-bar.log' if LEGACY else 'beambar.log')
PHONE_HOSTNAME = 'xgimi-remote' if LEGACY else 'beambar'
