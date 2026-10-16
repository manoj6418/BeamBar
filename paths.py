# Standard Library
import os
import sys
from pathlib import Path

# Inside the BeamBar.app built by py2app, code lives in a zip and files sit in Resources.
FROZEN = getattr(sys, 'frozen', None) == 'macosx_app'
RESOURCES = Path(os.environ['RESOURCEPATH']) if FROZEN else Path(__file__).resolve().parent
APP_BUNDLE = RESOURCES.parent.parent if FROZEN else None  # …/BeamBar.app

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
