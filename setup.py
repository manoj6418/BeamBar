"""Builds BeamBar.app with py2app: `.venv/bin/python setup.py py2app` (see make-dmg.sh)."""
# Third Party Library
from setuptools import setup

VERSION = '0.1.0'

setup(
    name='BeamBar',
    version=VERSION,
    app=['beambar_main.py'],
    data_files=[
        ('', ['pad.html', 'center.html']),
        ('assets', ['assets/icon-512.png', 'assets/menubar.png']),
    ],
    options={
        'py2app': {
            'iconfile': 'assets/BeamBar.icns',
            'includes': [
                'app', 'automations', 'caster', 'center', 'cli', 'commands', 'control', 'controller', 'hotkeys',
                'login_item', 'menu_views', 'net', 'pad', 'paths', 'phone', 'phone_qr', 'prompt', 'qr', 'search',
                'voice', 'UserNotifications',
            ],
            'packages': ['androidtvremote2', 'pychromecast', 'zeroconf', 'aiohttp', 'certifi'],
            'plist': {
                'CFBundleName': 'BeamBar',
                'CFBundleDisplayName': 'BeamBar',
                'CFBundleIdentifier': 'dev.beambar.app',
                'CFBundleShortVersionString': VERSION,
                'CFBundleVersion': VERSION,
                'LSUIElement': True,
                'LSMinimumSystemVersion': '13.0',
                'NSHumanReadableCopyright': 'Unofficial; not affiliated with XGIMI or Google.',
                'NSMicrophoneUsageDescription': 'Voice search sends what you say to your TV.',
                'NSLocalNetworkUsageDescription': 'BeamBar finds and controls your TV on your Wi-Fi.',
                'NSBonjourServices': ['_androidtvremote2._tcp', '_googlecast._tcp', '_http._tcp'],
                'NSAppleEventsUsageDescription': 'BeamBar reads the front browser tab when you send it to the TV.',
            },
        }
    },
)
