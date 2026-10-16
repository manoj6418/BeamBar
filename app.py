# Standard Library
import asyncio
import json
import logging
import re
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import parse_qs, quote_plus, urlparse

# Third Party Library
import automations
import caster
import commands
import control
import login_item
import search
import pychromecast
import rumps
from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth, VoiceSessionInProgress
from AppKit import (
    NSApplication,
    NSEvent,
    NSEventMaskScrollWheel,
    NSHapticFeedbackManager,
    NSOpenPanel,
    NSPasteboard,
    NSPasteboardTypeString,
    NSSound,
)
from PyObjCTools import AppHelper
from controller import GameController
from hotkeys import accessibility_trusted, DEFAULT_HOTKEYS, GlobalHotkeys
from phone import PhoneServer
from pad import build_pad
from pychromecast.controllers.youtube import YouTubeController
from voice import VoiceCapture

import net
from paths import CERT_FILE, CONFIG_DIR, CONFIG_FILE, KEY_FILE, LOG_FILE, PHONE_HOSTNAME

CLIENT_NAME = 'BeamBar'

DEFAULT_CONFIG = {
    # Empty until the first launch finds a device on the network.
    'name': '',
    'host': '',
    'apps': {
        'Netflix': 'https://www.netflix.com/title',
        'YouTube': 'https://www.youtube.com',
        'Prime Video': 'https://app.primevideo.com',
    },
    'scenes': {
        'Movie night': [{'launch': 'https://www.netflix.com/title'}, {'volume': 40}],
        'Bedtime': [{'volume': 15}, {'sleep_in': 30}],
    },
    'hotkeys': DEFAULT_HOTKEYS,
    'typing_mode': 'keys',
    'haptics': True,
    'sounds': False,
    'menubar': 'volume',
    'phone_remote': True,
    'controller': True,
    'tmdb_api_key': '',
    'devices': {},
    'automations': automations.EXAMPLE,
}

ACCESSORY_POLICY = 1
RETRY_SECONDS = 30
ICON = '📽'
YOUTUBE_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
KEY_FOR_CHAR = {
    **{str(d): f'KEYCODE_{d}' for d in range(10)},
    **{c: f'KEYCODE_{c.upper()}' for c in 'abcdefghijklmnopqrstuvwxyz'},
    ' ': 'KEYCODE_SPACE', '.': 'KEYCODE_PERIOD', ',': 'KEYCODE_COMMA', '-': 'KEYCODE_MINUS', '@': 'KEYCODE_AT',
    '/': 'KEYCODE_SLASH', '=': 'KEYCODE_EQUALS', ';': 'KEYCODE_SEMICOLON', "'": 'KEYCODE_APOSTROPHE',
    '+': 'KEYCODE_PLUS', '*': 'KEYCODE_STAR', '#': 'KEYCODE_POUND', '\\': 'KEYCODE_BACKSLASH',
}

logging.basicConfig(filename=LOG_FILE, level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
log = logging.getLogger('beambar')
logging.getLogger('zeroconf').setLevel(logging.ERROR)


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        return {**DEFAULT_CONFIG, **json.loads(CONFIG_FILE.read_text())}
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)


def save_config(config):
    CONFIG_FILE.write_text(json.dumps(config, indent=2))


def notify(subtitle, message):
    script = 'display notification item 1 of argv with title "BeamBar" subtitle item 2 of argv'
    subprocess.Popen(['osascript', '-e', f'on run argv\n{script}\nend run', message, subtitle])


def youtube_id(text):
    parsed = urlparse(text)
    if parsed.netloc.endswith('youtu.be'):
        return parsed.path.strip('/').split('/')[0]
    if 'youtube.com' in parsed.netloc:
        if parsed.path == '/watch':
            return parse_qs(parsed.query).get('v', [None])[0]
        for prefix in ('/shorts/', '/embed/', '/live/'):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix) :].split('/')[0]
    return None


class BeamBar(rumps.App):
    def __init__(self):
        super().__init__('BeamBar', title=ICON, quit_button=None)
        self.config = load_config()
        self.state = 'connecting'
        self.cast = None
        self.remote = None
        self.pad = None
        self.youtube = None
        self.sleep_deadline = None
        self.sleep_timer = None
        self.voice_session = None
        self.voice = VoiceCapture()
        self.media_server = caster.MediaServer()
        self.media_poll = 0

        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()

        self.status_item = rumps.MenuItem('Connecting…')
        self.app_menu = rumps.MenuItem('Apps')
        self.scene_menu = rumps.MenuItem('Scenes')
        self.login_item = rumps.MenuItem('Start at login', callback=self.toggle_login)
        self.hotkey_item = rumps.MenuItem('Global hotkeys (⌃⌥)', callback=self.toggle_hotkeys)
        self.menu = [
            self.status_item,
            None,
            rumps.MenuItem('Show remote', callback=self.show_pad, key='r'),
            rumps.MenuItem('Hide remote', callback=lambda _: self.pad and self.hide_pad(), key='w'),
            None,
            rumps.MenuItem('Play / Pause', callback=self.key_action('MEDIA_PLAY_PAUSE'), key='p'),
            self.volume_menu(),
            self.navigate_menu(),
            self.media_menu(),
            self.app_menu,
            self.scene_menu,
            rumps.MenuItem('Open link or search…', callback=lambda _: self.open_link(None), key='l'),
            rumps.MenuItem('Type text…', callback=self.type_text),
            rumps.MenuItem('Send current browser tab', callback=lambda _: self.send_tab(), key='t'),
            rumps.MenuItem('Mirror my screen (AirPlay)', callback=lambda _: self.mirror()),
            self.cast_menu(),
            self.devices_menu(),
            rumps.MenuItem('Phone remote link…', callback=self.phone_link),
            self.power_menu(),
            None,
            self.hotkey_item,
            self.login_item,
            rumps.MenuItem('Pair with projector…', callback=self.pair),
            rumps.MenuItem('Reconnect', callback=self.reconnect),
            rumps.MenuItem('Quit', callback=rumps.quit_application, key='q'),
        ]
        self.build_app_menu()
        self.build_scene_menu()
        self.login_item.state = login_item.is_installed()

        self.hotkeys = GlobalHotkeys(self.config.get('hotkeys'), self.hotkey_action)
        self.hotkey_item.state = self.hotkeys.start()

        net.device_host = self.config['host']
        self.remote = AndroidTVRemote(CLIENT_NAME, str(CERT_FILE), str(KEY_FILE), self.config['host'], loop=self.loop)
        threading.Thread(target=self.discover_and_connect, daemon=True).start()
        rumps.Timer(self.refresh, 1).start()
        if self.config.get('pad_open'):
            rumps.Timer(self.restore_pad, 1).start()
        self.control = control.ControlServer(self.on_control_request)
        self.control.start()
        self.scroll_acc = 0.0
        NSEvent.addLocalMonitorForEventsMatchingMask_handler_(NSEventMaskScrollWheel, self.on_menubar_scroll)
        self.phone = PhoneServer(self.on_phone_message, self.pad_status)
        if self.config.get('phone_remote', True):
            self.phone.start()
        self.automations = automations.Automations(lambda: self.config.get('automations', []), self.run_command, notify)
        self.controller = GameController(lambda key: AppHelper.callAfter(self.send_key, key), lambda name: notify('Controller', f'{name} connected'))
        if self.config.get('controller', True):
            self.controller.start()

    # ----- menus -----

    def volume_menu(self):
        menu = rumps.MenuItem('Volume')
        menu.add(rumps.MenuItem('Up', callback=self.key_action('VOLUME_UP'), key='='))
        menu.add(rumps.MenuItem('Down', callback=self.key_action('VOLUME_DOWN'), key='-'))
        menu.add(rumps.MenuItem('Mute / Unmute', callback=self.key_action('VOLUME_MUTE'), key='m'))
        menu.add(None)
        for level in range(0, 101, 10):
            menu.add(rumps.MenuItem(f'{level}', callback=self.volume_action(level)))
        menu.add(rumps.MenuItem('Set exact…', callback=self.volume_exact))
        return menu

    def navigate_menu(self):
        menu = rumps.MenuItem('Navigate')
        for label, key in (
            ('↑ Up', 'DPAD_UP'),
            ('↓ Down', 'DPAD_DOWN'),
            ('← Left', 'DPAD_LEFT'),
            ('→ Right', 'DPAD_RIGHT'),
            ('OK', 'DPAD_CENTER'),
            (None, None),
            ('Back', 'BACK'),
            ('Home', 'HOME'),
            ('Settings', 'SETTINGS'),
            ('Input source', 'TV_INPUT'),
        ):
            menu.add(rumps.MenuItem(label, callback=self.key_action(key)) if label else None)
        return menu

    def media_menu(self):
        menu = rumps.MenuItem('Media')
        menu.add(rumps.MenuItem('Back 10 s', callback=lambda _: self.media_action({'action': 'skip', 'delta': -10})))
        menu.add(rumps.MenuItem('Forward 10 s', callback=lambda _: self.media_action({'action': 'skip', 'delta': 10})))
        menu.add(None)
        for label, key in (
            ('Rewind', 'MEDIA_REWIND'),
            ('Fast forward', 'MEDIA_FAST_FORWARD'),
            ('Previous', 'MEDIA_PREVIOUS'),
            ('Next', 'MEDIA_NEXT'),
            ('Subtitles', 'CAPTIONS'),
        ):
            menu.add(rumps.MenuItem(label, callback=self.key_action(key)))
        return menu

    def cast_menu(self):
        menu = rumps.MenuItem('Cast from this Mac')
        menu.add(rumps.MenuItem('Cast a file…', callback=self.cast_file))
        menu.add(rumps.MenuItem('Cast a URL…', callback=self.cast_url))
        menu.add(rumps.MenuItem('Stop casting', callback=self.stop_casting))
        return menu

    def power_menu(self):
        menu = rumps.MenuItem('Power')
        menu.add(rumps.MenuItem('Wake', callback=lambda _: self.power_action({'action': 'wake'})))
        menu.add(rumps.MenuItem('Standby', callback=lambda _: self.power_action({'action': 'standby'})))
        menu.add(rumps.MenuItem('Power toggle', callback=self.key_action('POWER')))
        menu.add(None)
        for minutes in (15, 30, 60, 90):
            menu.add(
                rumps.MenuItem(
                    f'Sleep in {minutes} min',
                    callback=lambda _, m=minutes: self.power_action({'action': 'sleep', 'minutes': m}),
                )
            )
        menu.add(rumps.MenuItem('Cancel sleep timer', callback=lambda _: self.power_action({'action': 'cancel'})))
        return menu

    def build_app_menu(self):
        if self.app_menu._menu is not None:
            self.app_menu.clear()
        for label, link in sorted(self.config['apps'].items()):
            self.app_menu.add(rumps.MenuItem(label, callback=self.launch_action(link)))
        self.app_menu.add(None)
        self.app_menu.add(rumps.MenuItem('Add app…', callback=self.add_app))

    def build_scene_menu(self):
        if self.scene_menu._menu is not None:
            self.scene_menu.clear()
        for name in self.config.get('scenes', {}):
            self.scene_menu.add(rumps.MenuItem(name, callback=lambda _, n=name: self.run_scene(n)))
        self.scene_menu.add(None)
        self.scene_menu.add(
            rumps.MenuItem(
                'Edit scenes (config.json)…', callback=lambda _: subprocess.Popen(['open', str(CONFIG_FILE)])
            )
        )

    def devices_menu(self):
        menu = rumps.MenuItem('Devices')
        self.device_menu = menu
        self.build_device_menu()
        return menu

    def build_device_menu(self):
        if self.device_menu._menu is not None:
            self.device_menu.clear()
        current = self.config['name']
        self.device_menu.add(rumps.MenuItem(f'● {current}' if current else 'No device yet', callback=None))
        for name, info in self.config.get('devices', {}).items():
            if name != current:
                self.device_menu.add(rumps.MenuItem(name, callback=lambda _, n=name: self.switch_device(n)))
        self.device_menu.add(None)
        self.device_menu.add(rumps.MenuItem('Find devices on the network…', callback=self.find_devices))

    def find_devices(self, _):
        found = self.scan_devices()
        if not found:
            rumps.alert('Devices', 'No Android TV / Google TV devices answered on this network.')
            return
        devices = self.config.setdefault('devices', {})
        if self.config['name']:
            devices.setdefault(self.config['name'], {'host': self.config['host']})
        for name, host in found.items():
            devices[name] = {'host': host}
        save_config(self.config)
        self.build_device_menu()
        notify('Devices', 'Found: ' + ', '.join(found))

    @staticmethod
    def scan_devices(seconds=4):
        """Google TV / Android TV devices that answer on this network: name -> address."""
        from zeroconf import ServiceBrowser, Zeroconf

        found = {}

        class Listener:
            def add_service(self_, zc, kind, name):
                info = zc.get_service_info(kind, name)
                if info and info.parsed_addresses():
                    found[name.replace('._androidtvremote2._tcp.local.', '')] = info.parsed_addresses()[0]

            def update_service(self_, *args):
                pass

            def remove_service(self_, *args):
                pass

        zc = Zeroconf()
        ServiceBrowser(zc, '_androidtvremote2._tcp.local.', Listener())
        time.sleep(seconds)
        zc.close()
        return found

    def first_run_setup(self):
        """No device configured yet: pick the only one on the network, or ask."""
        found = self.scan_devices(seconds=6)
        if not found:
            notify('No TV or projector found', 'Turn it on, join the same Wi-Fi, then use Devices → Find devices…')
            return False
        self.config.setdefault('devices', {}).update({name: {'host': host} for name, host in found.items()})
        if len(found) > 1:
            save_config(self.config)
            AppHelper.callAfter(self.build_device_menu)
            notify('Pick your device', f'Found {len(found)}: choose one under Devices.')
            return False
        name, host = next(iter(found.items()))
        self.config['name'], self.config['host'] = name, host
        save_config(self.config)
        self.remote.host = host
        net.device_host = host
        AppHelper.callAfter(self.build_device_menu)
        log.info('first run: using %s at %s', name, host)
        return True

    def phone_link(self, _):
        url = self.phone.url()
        NSPasteboard.generalPasteboard().clearContents()
        NSPasteboard.generalPasteboard().setString_forType_(url, NSPasteboardTypeString)
        rumps.alert('Phone remote', f'Open this on any phone on your Wi-Fi (copied to clipboard):\n\n{url}\nor http://{PHONE_HOSTNAME}.local:8788\n\nAdd it to the home screen for an app-like remote.')

    def send_tab(self):
        script = """
tell application "System Events" to set frontApp to name of first process whose frontmost is true
if frontApp is "Safari" then
    tell application "Safari" to return URL of front document
else
    tell application "Google Chrome" to return URL of active tab of front window
end if
"""
        result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        url = result.stdout.strip()
        log.info('send tab: url=%r stderr=%r', url, result.stderr.strip()[:200])
        if not url.startswith('http'):
            if 'not allowed' in result.stderr or '-1743' in result.stderr:
                notify('Send tab', 'macOS blocked access to the browser. Allow "Python" under System Settings → Privacy → Automation.')
            else:
                notify('Send tab', 'No browser tab found in Chrome, Brave, Edge or Safari.')
            return
        host = urlparse(url).netloc.lower()
        playable = youtube_id(url) or any(k in host for k in ('netflix.com', 'primevideo.com', 'hotstar.com', 'jiocinema', 'youtube.com'))
        direct_media = url.lower().split('?')[0].endswith(caster.PLAYABLE)
        if playable:
            notify('Send tab', url[:80])
            self.open_link(url)
        elif direct_media:
            self.cast_media(url, None, url.rsplit('/', 1)[-1])
        else:
            notify('Send tab', 'The projector has no web browser for this page. In Chrome use ⋮ → Cast… → "Cast tab" instead.')

    def run_command(self, text):
        action = commands.parse(text)
        if action:
            AppHelper.callAfter(self.perform, action)

    def on_phone_message(self, msg):
        if msg.get('type') in ('drag', 'resize', 'close', 'haptic', 'mini'):
            return
        AppHelper.callAfter(self.on_pad_message, msg)

    def do_search(self, query):
        def run():
            results = search.search(query, self.config.get('tmdb_api_key') or None)
            payload = json.dumps({'query': query, 'results': results})
            if self.pad is not None:
                AppHelper.callAfter(
                    self.pad.webview.evaluateJavaScript_completionHandler_,
                    f'window.remote && window.remote.setSearchResults({payload})', None,
                )
            self.phone.push_search(query, results)

        threading.Thread(target=run, daemon=True).start()

    # ----- connections -----

    def discover_and_connect(self):
        if not self.config['host'] and not self.first_run_setup():
            self.state = 'offline'
            return
        try:
            casts, browser = pychromecast.get_listed_chromecasts(
                friendly_names=[self.config['name']], discovery_timeout=6
            )
            browser.stop_discovery()
            if casts and casts[0].cast_info.host and casts[0].cast_info.host != self.config['host']:
                host = casts[0].cast_info.host
                log.info('projector moved %s -> %s', self.config['host'], host)
                self.config['host'] = host
                save_config(self.config)
                self.remote.host = host
                net.device_host = host
            if self.cast is not None:
                self.cast.disconnect(blocking=False)
            self.cast = pychromecast.get_chromecast_from_host(
                (self.config['host'], 8009, None, None, self.config['name'])
            )
            self.youtube = YouTubeController()
            self.cast.register_handler(self.youtube)
            self.cast.wait(timeout=10)
        except Exception:
            log.exception('cast connection failed')
        asyncio.run_coroutine_threadsafe(self.connect_remote(), self.loop)

    async def connect_remote(self):
        await self.remote.async_generate_cert_if_missing()
        try:
            await self.remote.async_connect()
        except InvalidAuth:
            log.info('remote not paired')
            self.state = 'unpaired'
            return
        except (CannotConnect, ConnectionClosed, OSError) as exc:
            log.info('remote connect failed: %s', exc)
            self.state = 'offline'
            self.loop.call_later(RETRY_SECONDS, lambda: self.loop.create_task(self.connect_remote()))
            return
        log.info('remote connected: %s', self.remote.device_info)
        self.state = 'connected'
        self.remote.keep_reconnecting(self.on_invalid_auth)

    def on_invalid_auth(self):
        self.state = 'unpaired'

    def run_async(self, coro, timeout=20):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def on_loop(self, func, *args):
        self.loop.call_soon_threadsafe(func, *args)

    # ----- basic actions -----

    def send_key(self, key):
        if self.state != 'connected':
            self.notify_not_ready()
            return
        self.on_loop(self.remote.send_key_command, key)

    def key_action(self, key):
        return lambda _: self.send_key(key)

    def volume_action(self, level):
        return lambda _: self.set_volume(level)

    def launch_action(self, link):
        return lambda _: self.launch(link)

    def launch(self, link):
        if self.state != 'connected':
            self.notify_not_ready()
            return
        self.on_loop(self.remote.send_launch_app_command, link)

    def set_volume(self, level):
        if self.cast is None:
            notify('Volume', 'Projector not reachable over Cast yet.')
            return
        self.cast.set_volume(max(0, min(100, level)) / 100)

    def volume_exact(self, _):
        response = self.ask('Set volume', 'Volume level (0–100):', str(self.current_volume() or ''))
        if response and response.strip().isdigit():
            self.set_volume(int(response.strip()))

    def type_text(self, _):
        response = self.ask('Type on projector', 'Select a text box on the projector first, then type here:', '')
        if response and self.state == 'connected':
            self.on_loop(self.remote.send_text, response)

    def send_typing(self, msg):
        if self.state != 'connected':
            return
        mode = self.config.get('typing_mode', 'keys')
        if msg.get('backspace') or (not msg.get('char') and not msg.get('text')):
            self.on_loop(self.remote.send_key_command, 'DEL')
            return
        if mode == 'replace':
            self.on_loop(self.remote.send_text, msg.get('text', ''))
            return
        char = msg.get('char') or msg.get('text', '')[-1:]
        if not char:
            return
        keycode = KEY_FOR_CHAR.get(char)
        if keycode is not None and mode == 'keys':
            self.on_loop(self.remote.send_key_command, keycode)
        else:
            self.on_loop(self.remote.send_text, char)

    def add_app(self, _):
        label = self.ask('Add app', 'Menu name (e.g. JioHotstar):', '')
        if not label or not label.strip():
            return
        link = self.ask('Add app', f'Web link that opens {label.strip()} (e.g. https://www.hotstar.com):', 'https://')
        if link and link.strip().startswith(('http://', 'https://')):
            self.config['apps'][label.strip()] = link.strip()
            save_config(self.config)
            self.build_app_menu()

    # ----- links -----

    def clipboard_text(self):
        text = NSPasteboard.generalPasteboard().stringForType_(NSPasteboardTypeString)
        return (text or '').strip()

    def open_link(self, text):
        if not text:
            default = self.clipboard_text()
            default = default if default.startswith(('http://', 'https://')) else ''
            text = self.ask(
                'Open on projector', 'Paste a YouTube / Netflix / Prime link, or type a YouTube search:', default
            )
        if not text or not text.strip():
            return
        text = text.strip()
        if self.state != 'connected' and not youtube_id(text):
            self.notify_not_ready()
            return
        video = youtube_id(text) if text.startswith(('http://', 'https://')) else None
        if video and self.cast is not None and self.youtube is not None:
            threading.Thread(target=self.play_youtube, args=(video,), daemon=True).start()
        elif text.startswith(('http://', 'https://')):
            self.launch(text)
        else:
            self.launch(f'https://www.youtube.com/results?search_query={quote_plus(text)}')

    def play_youtube(self, video):
        try:
            self.youtube.play_video(video)
        except Exception:
            log.exception('youtube cast failed, falling back to app link')
            self.launch(f'https://www.youtube.com/watch?v={video}')

    # ----- now playing -----

    def media_status(self):
        if self.cast is None or self.cast.media_controller is None:
            return None
        status = self.cast.media_controller.status
        if not status or not status.media_session_id or not status.title:
            return None
        subtitle = status.series_title or ''
        if status.season is not None and status.episode is not None:
            subtitle = f'{subtitle} · S{status.season} E{status.episode}'.strip(' ·')
        if not subtitle and status.player_state == 'PAUSED':
            subtitle = 'Paused'
        images = status.images
        return {
            'title': status.title,
            'subtitle': subtitle,
            'image': images[0].url if images else None,
            'duration': status.duration,
            'position': status.adjusted_current_time,
            'state': status.player_state,
            'rate': status.playback_rate or 1,
        }

    def media_action(self, msg):
        controller = self.cast.media_controller if self.cast is not None else None
        active = controller is not None and controller.status and controller.status.media_session_id
        action = msg.get('action')
        if action == 'seek' and active:
            controller.seek(float(msg.get('position', 0)))
        elif action == 'skip':
            if active and controller.status.duration:
                controller.seek(max(0, controller.status.adjusted_current_time + float(msg.get('delta', 0))))
            else:
                self.send_key('MEDIA_FAST_FORWARD' if float(msg.get('delta', 0)) > 0 else 'MEDIA_REWIND')
        elif action == 'playpause':
            if active:
                controller.pause() if controller.status.player_state == 'PLAYING' else controller.play()
            else:
                self.send_key('MEDIA_PLAY_PAUSE')

    # ----- voice -----

    def voice_action(self, msg):
        if msg.get('action') == 'start':
            if self.state != 'connected':
                self.notify_not_ready()
                return
            try:
                self.voice_session = self.run_async(self.remote.start_voice(), timeout=5)
            except VoiceSessionInProgress:
                return
            except Exception as exc:
                log.warning('voice session failed: %s', exc)
                notify('Voice', 'The projector did not accept a voice session.')
                return
            session = self.voice_session
            try:
                self.voice.start(lambda chunk: self.on_loop(self.remote.send_voice_chunk, chunk, session))
            except Exception as exc:
                log.warning('mic failed: %s', exc)
                notify(
                    'Voice', 'Could not open the microphone. Allow Python under System Settings → Privacy → Microphone.'
                )
                self.on_loop(self.remote.end_voice, session)
                self.voice_session = None
        else:
            self.voice.stop()
            if self.voice_session is not None:
                self.on_loop(self.remote.end_voice, self.voice_session)
                self.voice_session = None

    # ----- scenes, sleep timer, power -----

    def run_scene(self, name):
        steps = self.config.get('scenes', {}).get(name)
        if not steps:
            return
        threading.Thread(target=self.run_steps, args=(name, steps), daemon=True).start()

    def run_steps(self, name, steps):
        log.info('scene %s: %s', name, steps)
        for step in steps:
            if 'launch' in step:
                self.launch(step['launch'])
            elif 'volume' in step:
                self.set_volume(int(step['volume']))
            elif 'key' in step:
                self.send_key(step['key'])
            elif 'sleep_in' in step:
                self.power_action({'action': 'sleep', 'minutes': int(step['sleep_in'])})
            elif 'standby' in step:
                self.power_action({'action': 'standby'})
            elif 'wait' in step:
                time.sleep(float(step['wait']))
                continue
            time.sleep(1.5)

    def power_action(self, msg):
        action = msg.get('action')
        if action == 'standby':
            self.cancel_sleep()
            self.send_key('SLEEP')
        elif action == 'wake':
            self.send_key('WAKEUP')
        elif action == 'sleep':
            minutes = int(msg.get('minutes') or 30)
            self.cancel_sleep()
            self.sleep_deadline = time.time() + minutes * 60
            self.sleep_timer = threading.Timer(minutes * 60, self.sleep_now)
            self.sleep_timer.daemon = True
            self.sleep_timer.start()
            notify('Sleep timer', f'Projector will go to standby in {minutes} minutes.')
        elif action == 'cancel':
            self.cancel_sleep()

    def sleep_now(self):
        self.sleep_deadline = None
        self.sleep_timer = None
        self.send_key('SLEEP')

    def cancel_sleep(self):
        if self.sleep_timer is not None:
            self.sleep_timer.cancel()
        self.sleep_timer = None
        self.sleep_deadline = None

    def sleep_in(self):
        if self.sleep_deadline is None:
            return None
        return max(0, round((self.sleep_deadline - time.time()) / 60))

    # ----- cast from mac -----

    def cast_file(self, _):
        log.info('cast file: opening file dialog')
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        panel = NSOpenPanel.openPanel()
        panel.setTitle_('Cast to projector')
        panel.setAllowedFileTypes_([ext.lstrip('.') for ext in caster.PLAYABLE])
        panel.setCanChooseDirectories_(False)
        panel.setAllowsMultipleSelection_(False)
        if panel.runModal() != 1 or not panel.URLs():
            return
        path = panel.URLs()[0].path()
        url = self.media_server.url_for(path)
        self.cast_media(url, caster.content_type_for(path), Path(path).name)

    def cast_url(self, _):
        default = self.clipboard_text()
        url = self.ask(
            'Cast a URL',
            'Direct MP4 / WebM / MP3 / M3U8 / image link (YouTube and Netflix links go through "Open link"):',
            default if default.startswith('http') else 'https://',
        )
        if not url or not url.strip().startswith('http'):
            return
        url = url.strip()
        host = urlparse(url).netloc.lower()
        if youtube_id(url) or any(k in host for k in ('netflix.com', 'primevideo.com', 'hotstar.com')):
            self.open_link(url)
            return
        self.cast_media(url, None, url.rsplit('/', 1)[-1])

    def cast_media(self, url, content_type, title):
        if self.cast is None:
            notify('Cast', 'Projector not reachable over Cast yet.')
            return

        def run():
            try:
                state = caster.play(self.cast, url, content_type, title)
                controller = self.cast.media_controller
                for _ in range(10):
                    time.sleep(1)
                    state = controller.status.player_state
                    if state in ('PLAYING', 'PAUSED') or (state == 'BUFFERING' and controller.status.current_time > 0):
                        break
                    if state == 'IDLE' and controller.status.idle_reason == 'ERROR':
                        break
                log.info('casting %s -> %s (%s)', url, state, controller.status.idle_reason)
                if state == 'IDLE' and controller.status.idle_reason == 'ERROR':
                    notify('Cast failed', 'The projector could not play this. Use a direct MP4/WebM/MP3/M3U8 link, or "Open link" for YouTube/Netflix.')
                    self.cast.quit_app()
                else:
                    notify('Casting', title or url)
            except Exception as exc:
                log.exception('cast failed')
                notify('Cast failed', str(exc)[:120])

        threading.Thread(target=run, daemon=True).start()

    def stop_casting(self, _):
        if self.cast is not None:
            self.cast.quit_app()

    # ----- hotkeys, login item -----

    def hotkey_action(self, action):
        if action == 'toggle_remote':
            if self.pad is not None and self.pad.isVisible():
                self.hide_pad()
            else:
                self.show_pad(None)
        elif action == 'VOLUME_UP':
            self.set_volume((self.current_volume() or 0) + 2)
        elif action == 'VOLUME_DOWN':
            self.set_volume((self.current_volume() or 0) - 2)
        else:
            self.send_key(action)

    def toggle_hotkeys(self, item):
        if self.hotkeys.active:
            self.hotkeys.stop()
            item.state = False
            return
        if not accessibility_trusted(prompt=True):
            rumps.alert(
                'Accessibility needed',
                'Allow "Python" under System Settings → Privacy & Security → Accessibility, then turn hotkeys on again.',
            )
            return
        item.state = self.hotkeys.start()

    def toggle_login(self, item):
        if login_item.is_installed():
            ok, err = login_item.uninstall()
            item.state = False
            if not ok and err:
                log.warning('launch agent removal: %s', err)
            return
        ok, err = login_item.install()
        if not ok:
            rumps.alert('Start at login failed', err or 'launchctl refused the LaunchAgent.')
            return
        item.state = True
        notify('Start at login', 'BeamBar will start automatically. Restarting now…')
        rumps.Timer(lambda t: rumps.quit_application(), 1.5).start()

    # ----- command dispatch (CLI, palette, hotkeys, automations) -----

    def on_control_request(self, request):
        action = commands.parse(request.get('command', '')) if 'command' in request else request.get('action')
        if not action:
            return {'ok': False, 'error': 'unknown command (try: beambar help)'}
        if action['type'] == 'status':
            return {'ok': True, 'result': self.pad_status()}
        if action['type'] == 'help':
            return {'ok': True, 'result': commands.HELP}
        AppHelper.callAfter(self.perform, action)
        return {'ok': True, 'result': action}

    def perform(self, action):
        kind = action.get('type')
        if kind == 'key':
            self.send_key(action['key'])
        elif kind == 'volume':
            self.set_volume(int(action['level']))
        elif kind == 'volume_delta':
            self.set_volume((self.current_volume() or 0) + int(action['delta']))
        elif kind == 'app':
            link = self.find_app(action['name'])
            if link:
                self.launch(link)
            else:
                notify('App', f"No app called {action['name']} in config.json")
        elif kind == 'openLink':
            self.open_link(action.get('text'))
        elif kind == 'text':
            self.on_loop(self.remote.send_text, action['text']) if self.state == 'connected' else self.notify_not_ready()
        elif kind == 'scene':
            self.run_scene(self.find_scene(action['name']))
        elif kind == 'power':
            self.power_action(action)
        elif kind == 'media':
            self.media_action(action)
        elif kind == 'cast':
            target = action['target']
            if target.startswith('http'):
                self.cast_media(target, None, target.rsplit('/', 1)[-1])
            else:
                self.cast_media(self.media_server.url_for(target), caster.content_type_for(target), Path(target).name)
        elif kind == 'remote':
            self.remote_action(action.get('action'))
        elif kind == 'focus':
            self.autofocus()
        elif kind == 'tab':
            self.send_tab()
        elif kind == 'mirror':
            self.mirror()
        elif kind == 'device':
            self.switch_device(action['name'])
        elif kind == 'haptic':
            self.haptic(action.get('kind', 'step'))
        elif kind == 'status':
            return self.pad_status()

    def find_app(self, name):
        for label, link in self.config['apps'].items():
            if label.lower() == name.lower():
                return link
        for label, link in self.config['apps'].items():
            if name.lower() in label.lower():
                return link
        return None

    def find_scene(self, name):
        for scene in self.config.get('scenes', {}):
            if scene.lower() == name.lower() or name.lower() in scene.lower():
                return scene
        return name

    def remote_action(self, what):
        visible = self.pad is not None and self.pad.isVisible()
        if what == 'show' or (what == 'toggle' and not visible):
            self.show_pad(None)
        elif what == 'hide' or (what == 'toggle' and visible):
            if self.pad is not None:
                self.hide_pad()
        elif what == 'mini':
            self.config['pad_mini'] = not self.config.get('pad_mini')
            save_config(self.config)
            if self.pad is not None:
                self.pad.webview.evaluateJavaScript_completionHandler_(
                    f"window.remote && window.remote.setMini({'true' if self.config['pad_mini'] else 'false'})", None
                )

    def mirror(self):
        if self.state != 'connected':
            self.notify_not_ready()
            return
        link = self.config.get('airplay_app_link', 'https://play.google.com/store/apps/details?id=com.ionitech.airscreen')

        def run():
            self.on_loop(self.remote.send_launch_app_command, link)
            time.sleep(2.5)
            if self.remote.current_app == 'com.android.vending':
                self.on_loop(self.remote.send_key_command, 'DPAD_CENTER')
                time.sleep(2.5)
            notify('Mirror', 'AirScreen is starting on the projector. Pick it under Screen Mirroring.')
            script = """
tell application "System Events"
    tell process "ControlCenter"
        if (count of windows) is 0 then
            click (first menu bar item of menu bar 1 whose description is "Control Centre" or description is "Control Center")
            delay 1.2
        end if
        set tile to missing value
        repeat with e in (entire contents of window 1)
            try
                if (value of attribute "AXIdentifier" of e as string) is "controlcenter-screen-mirroring" then
                    set tile to e
                    exit repeat
                end if
            end try
        end repeat
        if tile is not missing value then click tile
        delay 2
        repeat with e in (entire contents of window 1)
            try
                if (name of e as string) contains "AS-H0030" then
                    click e
                    exit repeat
                end if
            end try
        end repeat
    end tell
end tell
"""
            subprocess.run(['osascript', '-e', script], capture_output=True, text=True)

        threading.Thread(target=run, daemon=True).start()

    def autofocus(self):
        notify('Autofocus', 'Needs ADB on the projector (not enabled yet).')

    def switch_device(self, name):
        devices = self.config.get('devices', {})
        match = next((n for n in devices if n.lower() == name.lower() or name.lower() in n.lower()), None)
        if match is None:
            notify('Devices', f'No device called {name}. Use Devices → Find devices on the network…')
            return
        if self.config['name']:
            devices.setdefault(self.config['name'], {'host': self.config['host']})
        self.config['name'] = match
        self.config['host'] = devices[match]['host']
        net.device_host = self.config['host']
        save_config(self.config)
        self.build_device_menu()
        self.state = 'connecting'
        self.on_loop(self.remote.disconnect)
        self.remote = AndroidTVRemote(CLIENT_NAME, str(CERT_FILE), str(KEY_FILE), self.config['host'], loop=self.loop)
        threading.Thread(target=self.discover_and_connect, daemon=True).start()
        notify('Devices', f'Switching to {match}…')

    def haptic(self, kind='step'):
        if self.config.get('haptics'):
            pattern = {'step': 1, 'press': 0, 'edge': 2}.get(kind, 0)
            NSHapticFeedbackManager.defaultPerformer().performFeedbackPattern_performanceTime_(pattern, 1)
        if self.config.get('sounds'):
            sound = NSSound.soundNamed_('Tink' if kind == 'step' else 'Pop')
            if sound is not None:
                sound.play()

    def on_menubar_scroll(self, event):
        button = getattr(self._nsapp.nsstatusitem, 'button', lambda: None)()
        if button is None or event.window() != button.window():
            return event
        self.scroll_acc += event.scrollingDeltaY()
        if abs(self.scroll_acc) >= 8:
            steps = int(self.scroll_acc / 8)
            self.scroll_acc -= steps * 8
            self.set_volume((self.current_volume() or 0) + steps * 2)
        return None

    # ----- pad -----

    def show_pad(self, _):
        if self.pad is None:
            self.pad = build_pad(self.on_pad_message)
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.pad.makeKeyAndOrderFront_(None)
        self.pad.push_status(self.pad_status())
        self.remember_pad(True)

    def hide_pad(self):
        self.pad.orderOut_(None)
        self.remember_pad(False)

    def remember_pad(self, is_open):
        if self.config.get('pad_open') != is_open:
            self.config['pad_open'] = is_open
            save_config(self.config)

    def restore_pad(self, timer):
        timer.stop()
        self.show_pad(None)

    def on_pad_message(self, msg):
        kind = msg.get('type')
        if kind == 'key':
            self.send_key(msg['key'])
        elif kind == 'volume':
            self.set_volume(int(msg['level']))
        elif kind == 'launch':
            self.launch(msg['link'])
        elif kind == 'openLink':
            self.open_link(msg.get('text'))
        elif kind == 'text':
            self.send_typing(msg)
        elif kind == 'media':
            self.media_action(msg)
        elif kind == 'voice':
            self.voice_action(msg)
        elif kind == 'scene':
            self.run_scene(msg.get('name'))
        elif kind == 'power':
            self.power_action(msg)
        elif kind == 'addApp':
            self.add_app(None)
        elif kind == 'type':
            self.type_text(None)
        elif kind == 'pair':
            self.pair(None)
        elif kind == 'reconnect':
            self.reconnect(None)
        elif kind == 'drag':
            self.pad.begin_drag()
        elif kind == 'resize':
            self.pad.resize_to(int(msg.get('height', 0)))
        elif kind == 'mini':
            self.config['pad_mini'] = bool(msg.get('on'))
            save_config(self.config)
        elif kind == 'command':
            self.perform(commands.parse(msg.get('text', '')) or {})
        elif kind == 'search':
            self.do_search(msg.get('query', ''))
        elif kind == 'tab':
            self.send_tab()
        elif kind == 'haptic':
            self.haptic(msg.get('kind', 'step'))
        elif kind == 'close':
            self.hide_pad()

    def pad_status(self):
        cast_status = self.cast.status if self.cast is not None else None
        return {
            'state': self.state,
            'name': self.config['name'],
            'app': cast_status.display_name if cast_status else None,
            'volume': self.current_volume(),
            'muted': bool(cast_status.volume_muted) if cast_status else False,
            'apps': [{'label': label, 'link': link} for label, link in sorted(self.config['apps'].items())],
            'scenes': list(self.config.get('scenes', {})),
            'media': self.media_status(),
            'sleep_in': self.sleep_in(),
            'listening': self.voice.active,
            'mini': bool(self.config.get('pad_mini')),
            'commands': commands.suggestions(self.config),
            'devices': [n for n in self.config.get('devices', {}) if n != self.config['name']],
            'phone_url': self.phone.url() if self.config.get('phone_remote', True) else None,
        }

    # ----- misc -----

    def pair(self, _):
        try:
            self.run_async(self.remote.async_generate_cert_if_missing())
            self.run_async(self.remote.async_start_pairing())
        except (CannotConnect, ConnectionClosed, OSError, TimeoutError) as exc:
            rumps.alert('Pairing failed', f'Could not reach the projector: {exc}')
            return
        code = self.ask('Pair with projector', 'Enter the code shown on the projector screen:', '')
        if not code:
            return
        try:
            self.run_async(self.remote.async_finish_pairing(code.strip().upper()))
        except (InvalidAuth, ConnectionClosed, TimeoutError) as exc:
            rumps.alert('Pairing failed', f'The projector rejected the code: {exc}')
            return
        self.state = 'connecting'
        asyncio.run_coroutine_threadsafe(self.connect_remote(), self.loop)
        notify('Paired', 'Your Mac can now control the projector.')

    def reconnect(self, _):
        self.state = 'connecting'
        self.on_loop(self.remote.disconnect)
        threading.Thread(target=self.discover_and_connect, daemon=True).start()

    def ask(self, title, message, default):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        window = rumps.Window(message=message, title=title, default_text=default, cancel=True, dimensions=(260, 24))
        result = window.run()
        return result.text if result.clicked else None

    def notify_not_ready(self):
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        if self.state == 'unpaired':
            if rumps.alert(
                'Not paired yet',
                'Your Mac needs a one-time pairing before it can send buttons to the projector.',
                ok='Pair now',
                cancel='Later',
            ):
                self.pair(None)
            return
        reasons = {
            'offline': 'The projector is off or not on Wi-Fi. Retrying every 30 seconds.',
            'connecting': 'Still connecting, try again in a moment.',
        }
        rumps.alert('Not connected', reasons.get(self.state, self.state))

    def current_volume(self):
        if self.cast is not None and self.cast.status is not None:
            return round(self.cast.status.volume_level * 100)
        if self.state == 'connected' and self.remote.volume_info:
            info = self.remote.volume_info
            return round(info['level'] * 100 / info['max']) if info['max'] else None
        return None

    def refresh(self, _):
        volume = self.current_volume()
        app_name = self.cast.status.display_name if self.cast is not None and self.cast.status else None
        muted = bool(self.cast.status.volume_muted) if self.cast is not None and self.cast.status else False
        if self.cast is not None and time.time() - self.media_poll > 10 and self.cast.media_controller.is_active:
            self.media_poll = time.time()
            try:
                self.cast.media_controller.update_status()
            except Exception:
                pass
        labels = {
            'connected': self.config['name'],
            'unpaired': 'Not paired — use "Pair with projector…"',
            'offline': 'Projector offline',
            'connecting': 'Connecting…',
        }
        parts = [labels[self.state]]
        if self.state == 'connected':
            if app_name:
                parts.append(app_name)
            if volume is not None:
                parts.append('muted' if muted else f'vol {volume}')
            if self.sleep_in() is not None:
                parts.append(f'sleep in {self.sleep_in()} min')
        self.status_item.title = ' · '.join(parts)
        status = self.pad_status()
        if self.pad is not None and self.pad.isVisible():
            self.pad.push_status(status)
        self.phone.push_status(status)
        media = self.cast.media_controller.status if self.cast is not None else None
        self.automations.observe(self.state == 'connected', app_name, media.player_state if media and media.media_session_id else None, media.idle_reason if media else None)
        if self.state != 'connected':
            self.title = f'{ICON} !'
        elif self.config.get('menubar') == 'nowplaying' and self.media_status():
            media = self.media_status()
            mark = '▶' if media['state'] == 'PLAYING' else '⏸'
            self.title = f"{ICON} {mark} {media['title'][:22]}"
        else:
            self.title = f'{ICON} {volume}' if volume is not None else ICON


if __name__ == '__main__':
    NSApplication.sharedApplication().setActivationPolicy_(ACCESSORY_POLICY)
    BeamBar().run()
