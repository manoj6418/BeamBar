# Standard Library
import os
import plistlib
import subprocess
import sys
from pathlib import Path

# Third Party Library
from paths import APP_BUNDLE, FROZEN
from paths import LOG_FILE as LOG

LABEL = 'dev.beambar.app'
LEGACY_LABEL = 'com.manoj.xgimi-bar'  # login items made before the rename
AGENTS = Path.home() / 'Library' / 'LaunchAgents'
PLIST = AGENTS / f'{LABEL}.plist'
LEGACY_PLIST = AGENTS / f'{LEGACY_LABEL}.plist'
APP_DIR = Path(__file__).resolve().parent


def domain():
    return f'gui/{os.getuid()}'


def is_installed():
    return PLIST.exists() or LEGACY_PLIST.exists()


def active_label():
    return LEGACY_LABEL if LEGACY_PLIST.exists() and not PLIST.exists() else LABEL


def install():
    if LEGACY_PLIST.exists():
        subprocess.run(['launchctl', 'bootout', domain(), str(LEGACY_PLIST)], capture_output=True)
        LEGACY_PLIST.unlink()
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    plist = {
        'Label': LABEL,
        'ProgramArguments': ([str(APP_BUNDLE / 'Contents' / 'MacOS' / 'BeamBar')] if FROZEN
                             else [sys.executable, str(APP_DIR / 'app.py')]),
        'WorkingDirectory': str(APP_DIR),
        'RunAtLoad': True,
        'KeepAlive': {'SuccessfulExit': False},
        'ProcessType': 'Interactive',
        'StandardOutPath': str(LOG),
        'StandardErrorPath': str(LOG),
    }
    PLIST.write_bytes(plistlib.dumps(plist))
    subprocess.run(['launchctl', 'bootout', domain(), str(PLIST)], capture_output=True)
    result = subprocess.run(['launchctl', 'bootstrap', domain(), str(PLIST)], capture_output=True, text=True)
    return result.returncode == 0, result.stderr.strip()


def uninstall():
    ok, error = True, ''
    for plist in (PLIST, LEGACY_PLIST):
        if plist.exists():
            result = subprocess.run(['launchctl', 'bootout', domain(), str(plist)], capture_output=True, text=True)
            ok, error = ok and result.returncode == 0, error or result.stderr.strip()
            plist.unlink()
    return ok, error


def restart_via_launchd():
    subprocess.run(['launchctl', 'kickstart', '-k', f'{domain()}/{active_label()}'], capture_output=True)
