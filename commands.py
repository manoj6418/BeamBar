# Standard Library
import re
import shlex

KEY_WORDS = {
    'up': 'DPAD_UP',
    'down': 'DPAD_DOWN',
    'left': 'DPAD_LEFT',
    'right': 'DPAD_RIGHT',
    'ok': 'DPAD_CENTER',
    'select': 'DPAD_CENTER',
    'enter': 'DPAD_CENTER',
    'back': 'BACK',
    'home': 'HOME',
    'menu': 'MENU',
    'settings': 'SETTINGS',
    'input': 'TV_INPUT',
    'source': 'TV_INPUT',
    'play': 'MEDIA_PLAY',
    'pause': 'MEDIA_PAUSE',
    'playpause': 'MEDIA_PLAY_PAUSE',
    'toggle': 'MEDIA_PLAY_PAUSE',
    'stop': 'MEDIA_STOP',
    'next': 'MEDIA_NEXT',
    'previous': 'MEDIA_PREVIOUS',
    'prev': 'MEDIA_PREVIOUS',
    'rewind': 'MEDIA_REWIND',
    'forward': 'MEDIA_FAST_FORWARD',
    'ff': 'MEDIA_FAST_FORWARD',
    'subtitles': 'CAPTIONS',
    'captions': 'CAPTIONS',
    'search': 'SEARCH',
    'assistant': 'SEARCH',
}
POWER_WORDS = {
    'standby': 'standby',
    'off': 'standby',
    'sleep': 'sleep',
    'wake': 'wake',
    'on': 'wake',
    'power': 'toggle',
}
NUMBER = re.compile(r'^[+-]?\d+$')

HELP = '''commands:
  up / down / left / right / ok / back / home / settings / input
  play / pause / playpause / next / previous / rewind / forward / subtitles
  volume <0-100> | volume +5 | volume -5 | mute | unmute
  app <name>               open Netflix / YouTube / Prime Video (or any configured app)
  open <link or search>    YouTube/Netflix/Prime link, or a YouTube search
  type <text>              type into the focused field on the TV
  scene <name>             run a scene from config.json
  sleep <minutes> | sleep cancel | standby | wake
  skip <+/-seconds> | seek <seconds>
  cast <file or url>       play a local file or stream on the TV
  remote show | hide | toggle | mini
  phone                    show a QR code to open the phone remote
  center                   open the control center under the menu bar icon
  find                     search the network for TVs and add them to Devices
  status                   current TV state as JSON'''


def parse(text):
    """Turn a command line like 'volume 40' or 'open stranger things' into an action dict."""
    text = (text or '').strip()
    if not text:
        return None
    try:
        words = shlex.split(text)
    except ValueError:
        words = text.split()
    head = words[0].lower()
    rest = ' '.join(words[1:]).strip()
    lower_rest = rest.lower()

    if head in ('help', '?'):
        return {'type': 'help'}
    if head in ('status', 'state'):
        return {'type': 'status'}
    if head in KEY_WORDS and not rest:
        return {'type': 'key', 'key': KEY_WORDS[head]}
    if head in ('key', 'press') and rest:
        return {'type': 'key', 'key': rest.upper().replace('KEYCODE_', '')}
    if head in ('volume', 'vol', 'v'):
        if lower_rest in ('up', '+'):
            return {'type': 'volume_delta', 'delta': 5}
        if lower_rest in ('down', '-'):
            return {'type': 'volume_delta', 'delta': -5}
        if NUMBER.match(rest):
            if rest[0] in '+-':
                return {'type': 'volume_delta', 'delta': int(rest)}
            return {'type': 'volume', 'level': int(rest)}
        if lower_rest in ('mute', 'unmute'):
            return {'type': 'key', 'key': 'VOLUME_MUTE'}
        return None
    if head in ('mute', 'unmute'):
        return {'type': 'key', 'key': 'VOLUME_MUTE'}
    if head in ('app', 'launch') and rest:
        return {'type': 'app', 'name': rest}
    if head in ('open', 'play', 'watch', 'search', 'yt', 'youtube') and rest:
        return {'type': 'openLink', 'text': rest}
    if head in ('type', 'text') and rest:
        return {'type': 'text', 'text': rest}
    if head == 'scene' and rest:
        return {'type': 'scene', 'name': rest}
    if head in ('sleep', 'timer'):
        if lower_rest in ('cancel', 'off', 'stop'):
            return {'type': 'power', 'action': 'cancel'}
        if NUMBER.match(rest):
            return {'type': 'power', 'action': 'sleep', 'minutes': int(rest)}
        return {'type': 'power', 'action': 'sleep', 'minutes': 30}
    if head in POWER_WORDS:
        action = POWER_WORDS[head]
        if action == 'toggle':
            return {'type': 'key', 'key': 'POWER'}
        return {'type': 'power', 'action': action}
    if head == 'skip' and NUMBER.match(rest):
        return {'type': 'media', 'action': 'skip', 'delta': int(rest)}
    if head == 'seek' and NUMBER.match(rest):
        return {'type': 'media', 'action': 'seek', 'position': int(rest)}
    if head == 'cast' and rest:
        return {'type': 'cast', 'target': rest}
    if head == 'phone':
        return {'type': 'phone'}
    if head == 'center':
        return {'type': 'center'}
    if head == 'remote':
        if lower_rest in ('show', 'open'):
            return {'type': 'remote', 'action': 'show'}
        if lower_rest in ('hide', 'close'):
            return {'type': 'remote', 'action': 'hide'}
        if lower_rest in ('mini', 'collapse', 'expand'):
            return {'type': 'remote', 'action': 'mini'}
        return {'type': 'remote', 'action': 'toggle'}
    if head in ('focus', 'autofocus'):
        return {'type': 'focus'}
    if head in ('tab', 'browser'):
        return {'type': 'tab'}
    if head in ('find', 'devices', 'discover'):
        return {'type': 'find'}
    if head in ('mirror', 'airplay', 'screen'):
        return {'type': 'mirror'}
    if head in ('device', 'switch') and rest:
        return {'type': 'device', 'name': rest}
    return {'type': 'openLink', 'text': text}


def suggestions(config):
    """Static command list for the command palette (label, command)."""
    items = [
        ('Play / Pause', 'playpause'),
        ('Pause', 'pause'),
        ('Play', 'play'),
        ('Mute / Unmute', 'mute'),
        ('Volume 20', 'volume 20'),
        ('Volume 40', 'volume 40'),
        ('Volume 60', 'volume 60'),
        ('Home', 'home'),
        ('Back', 'back'),
        ('Settings', 'settings'),
        ('Input source', 'input'),
        ('Subtitles', 'subtitles'),
        ('Next', 'next'),
        ('Previous', 'previous'),
        ('Skip forward 30 s', 'skip 30'),
        ('Skip back 30 s', 'skip -30'),
        ('Sleep in 30 min', 'sleep 30'),
        ('Sleep in 60 min', 'sleep 60'),
        ('Cancel sleep timer', 'sleep cancel'),
        ('Standby', 'standby'),
        ('Wake', 'wake'),
        ('Mirror my screen (AirPlay)', 'mirror'),
        ('Collapse / expand remote', 'remote mini'),
        ('Hide remote', 'remote hide'),
    ]
    for name in sorted(config.get('apps', {})):
        items.append((f'Open {name}', f'app {name}'))
    for name in config.get('scenes', {}):
        items.append((f'Scene: {name}', f'scene {name}'))
    for name in config.get('devices', {}):
        items.append((f'Switch to {name}', f'device {name}'))
    return items
