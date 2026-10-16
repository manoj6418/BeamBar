# Standard Library
import logging
import time
from datetime import datetime

# Third Party Library
from AppKit import NSWorkspace
from Foundation import NSDistributedNotificationCenter, NSObject

log = logging.getLogger('beambar.automations')

TRIGGERS = (
    'projector_online',
    'projector_offline',
    'app_changed',
    'media_ended',
    'media_started',
    'mac_sleep',
    'mac_wake',
    'mac_lock',
    'mac_unlock',
    'time',
)

EXAMPLE = [
    {'when': 'time', 'at': '23:30', 'do': 'sleep 30', 'enabled': False},
    {'when': 'mac_sleep', 'do': 'standby', 'enabled': False},
    {'when': 'projector_online', 'do': 'remote show', 'enabled': False},
    {'when': 'media_ended', 'do': 'notify Episode finished', 'enabled': False},
]


class MacEvents(NSObject):
    def initWithHandler_(self, handler):
        self = self.init()
        self.handler = handler
        center = NSWorkspace.sharedWorkspace().notificationCenter()
        center.addObserver_selector_name_object_(self, 'onSleep:', 'NSWorkspaceWillSleepNotification', None)
        center.addObserver_selector_name_object_(self, 'onWake:', 'NSWorkspaceDidWakeNotification', None)
        dist = NSDistributedNotificationCenter.defaultCenter()
        dist.addObserver_selector_name_object_(self, 'onLock:', 'com.apple.screenIsLocked', None)
        dist.addObserver_selector_name_object_(self, 'onUnlock:', 'com.apple.screenIsUnlocked', None)
        return self

    def onSleep_(self, note):
        self.handler('mac_sleep')

    def onWake_(self, note):
        self.handler('mac_wake')

    def onLock_(self, note):
        self.handler('mac_lock')

    def onUnlock_(self, note):
        self.handler('mac_unlock')


class Automations:
    """Evaluates the `automations` list from config.json against state changes and the clock."""

    def __init__(self, rules_provider, run_command, notify):
        self.rules_provider = rules_provider
        self.run_command = run_command
        self.notify = notify
        self.last = {'online': None, 'app': None, 'media_state': None}
        self.fired_today = {}
        self.mac_events = MacEvents.alloc().initWithHandler_(lambda event: self.fire(event))

    def fire(self, event, **context):
        for rule in self.rules_provider():
            if rule.get('enabled', True) is False or rule.get('when') != event:
                continue
            if rule.get('app') and context.get('app') and rule['app'].lower() not in context['app'].lower():
                continue
            command = rule.get('do', '')
            log.info('automation %s -> %s', event, command)
            if command.startswith('notify '):
                self.notify('Automation', command[7:])
            else:
                self.run_command(command)

    def observe(self, online, app, media_state, media_idle_reason=None):
        if self.last['online'] is not None and online != self.last['online']:
            self.fire('projector_online' if online else 'projector_offline')
        if app and app != self.last['app'] and self.last['app'] is not None:
            self.fire('app_changed', app=app)
        if media_state != self.last['media_state']:
            if media_state == 'PLAYING' and self.last['media_state'] in (None, 'IDLE', 'BUFFERING'):
                self.fire('media_started', app=app)
            if media_state == 'IDLE' and self.last['media_state'] == 'PLAYING' and media_idle_reason == 'FINISHED':
                self.fire('media_ended', app=app)
        self.last = {'online': online, 'app': app, 'media_state': media_state}
        self.check_clock()

    def check_clock(self):
        now = datetime.now()
        stamp = now.strftime('%H:%M')
        today = now.date().isoformat()
        for index, rule in enumerate(self.rules_provider()):
            if rule.get('when') != 'time' or rule.get('enabled', True) is False:
                continue
            key = (index, rule.get('at'))
            if rule.get('at') == stamp and self.fired_today.get(key) != today:
                self.fired_today[key] = today
                self.run_rule(rule)

    def run_rule(self, rule):
        command = rule.get('do', '')
        log.info('automation time %s -> %s', rule.get('at'), command)
        if command.startswith('notify '):
            self.notify('Automation', command[7:])
        else:
            self.run_command(command)
