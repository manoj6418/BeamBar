# Standard Library
import logging

# Third Party Library
import Quartz
from ApplicationServices import AXIsProcessTrustedWithOptions, kAXTrustedCheckOptionPrompt

log = logging.getLogger('beambar.hotkeys')

KEYCODES = {
    'up': 126,
    'down': 125,
    'left': 123,
    'right': 124,
    'return': 36,
    'space': 49,
    'delete': 51,
    'escape': 53,
    'tab': 48,
    '=': 24,
    '-': 27,
    '[': 33,
    ']': 30,
    ',': 43,
    '.': 47,
    '/': 44,
    'a': 0,
    's': 1,
    'd': 2,
    'f': 3,
    'h': 4,
    'g': 5,
    'z': 6,
    'x': 7,
    'c': 8,
    'v': 9,
    'b': 11,
    'q': 12,
    'w': 13,
    'e': 14,
    'r': 15,
    'y': 16,
    't': 17,
    '1': 18,
    '2': 19,
    '3': 20,
    '4': 21,
    '6': 22,
    '5': 23,
    '9': 25,
    '7': 26,
    '8': 28,
    '0': 29,
    'o': 31,
    'u': 32,
    'i': 34,
    'p': 35,
    'l': 37,
    'j': 38,
    'k': 40,
    'n': 45,
    'm': 46,
}
MODIFIERS = {
    'ctrl': Quartz.kCGEventFlagMaskControl,
    'control': Quartz.kCGEventFlagMaskControl,
    'alt': Quartz.kCGEventFlagMaskAlternate,
    'option': Quartz.kCGEventFlagMaskAlternate,
    'cmd': Quartz.kCGEventFlagMaskCommand,
    'command': Quartz.kCGEventFlagMaskCommand,
    'shift': Quartz.kCGEventFlagMaskShift,
}
ALL_MODIFIER_FLAGS = (
    Quartz.kCGEventFlagMaskControl
    | Quartz.kCGEventFlagMaskAlternate
    | Quartz.kCGEventFlagMaskCommand
    | Quartz.kCGEventFlagMaskShift
)

DEFAULT_HOTKEYS = {
    'modifiers': 'ctrl+alt',
    'keys': {
        'up': 'DPAD_UP',
        'down': 'DPAD_DOWN',
        'left': 'DPAD_LEFT',
        'right': 'DPAD_RIGHT',
        'return': 'DPAD_CENTER',
        'delete': 'BACK',
        'space': 'MEDIA_PLAY_PAUSE',
        'h': 'HOME',
        'm': 'VOLUME_MUTE',
        '=': 'VOLUME_UP',
        '-': 'VOLUME_DOWN',
        'r': 'toggle_remote',
    },
}


def accessibility_trusted(prompt=False):
    return bool(AXIsProcessTrustedWithOptions({kAXTrustedCheckOptionPrompt: prompt}))


class GlobalHotkeys:
    def __init__(self, config, on_action):
        self.on_action = on_action
        self.tap = None
        self.source = None
        self.configure(config)

    def configure(self, config):
        config = {**DEFAULT_HOTKEYS, **(config or {})}
        self.flags = 0
        for name in config['modifiers'].lower().split('+'):
            self.flags |= MODIFIERS.get(name.strip(), 0)
        self.bindings = {}
        for key, action in config['keys'].items():
            code = KEYCODES.get(str(key).lower())
            if code is not None:
                self.bindings[code] = action

    def start(self):
        if self.tap is not None:
            return True
        if not accessibility_trusted():
            return False
        mask = Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown)
        self.tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            mask,
            self._callback,
            None,
        )
        if self.tap is None:
            log.warning('event tap could not be created')
            return False
        self.source = Quartz.CFMachPortCreateRunLoopSource(None, self.tap, 0)
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetMain(), self.source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(self.tap, True)
        log.info('global hotkeys enabled (%d bindings)', len(self.bindings))
        return True

    def stop(self):
        if self.tap is None:
            return
        Quartz.CGEventTapEnable(self.tap, False)
        Quartz.CFRunLoopRemoveSource(Quartz.CFRunLoopGetMain(), self.source, Quartz.kCFRunLoopCommonModes)
        self.tap = None
        self.source = None

    @property
    def active(self):
        return self.tap is not None

    def _callback(self, proxy, event_type, event, refcon):
        if event_type in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
            Quartz.CGEventTapEnable(self.tap, True)
            return event
        if event_type != Quartz.kCGEventKeyDown:
            return event
        if (Quartz.CGEventGetFlags(event) & ALL_MODIFIER_FLAGS) != self.flags:
            return event
        code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
        action = self.bindings.get(code)
        if action is None:
            return event
        try:
            self.on_action(action)
        except Exception:
            log.exception('hotkey action failed')
        return None
