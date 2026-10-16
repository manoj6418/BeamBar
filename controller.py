# Standard Library
import logging
import os
import threading
import time

os.environ.setdefault('PYGAME_HIDE_SUPPORT_PROMPT', '1')
os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')

log = logging.getLogger('beambar.controller')

BUTTONS = {
    0: 'DPAD_CENTER',  # A / Cross
    1: 'BACK',  # B / Circle
    2: 'MEDIA_PLAY_PAUSE',  # X / Square
    3: 'HOME',  # Y / Triangle
    4: 'BACK',  # Back / Share
    6: 'HOME',  # Start / Options
    9: 'VOLUME_DOWN',  # LB / L1
    10: 'VOLUME_UP',  # RB / R1
    11: 'DPAD_UP',
    12: 'DPAD_DOWN',
    13: 'DPAD_LEFT',
    14: 'DPAD_RIGHT',
}
HAT = {(0, 1): 'DPAD_UP', (0, -1): 'DPAD_DOWN', (-1, 0): 'DPAD_LEFT', (1, 0): 'DPAD_RIGHT'}
DEADZONE = 0.55
REPEAT_SECONDS = 0.28


class GameController:
    """Polls any connected game controller (Xbox, PlayStation, Switch Pro) and maps it to remote keys."""

    def __init__(self, send_key, on_connect=None):
        self.send_key = send_key
        self.on_connect = on_connect
        self.running = False

    def start(self):
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()

    def stop(self):
        self.running = False

    def loop(self):
        try:
            # Third Party Library
            import pygame
        except ImportError:
            log.warning('pygame not installed; controller support off')
            return
        pygame.init()
        pygame.joystick.init()
        joysticks = {}
        last_axis = {}
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.JOYDEVICEADDED:
                    joystick = pygame.joystick.Joystick(event.device_index)
                    joysticks[joystick.get_instance_id()] = joystick
                    log.info('controller connected: %s', joystick.get_name())
                    if self.on_connect:
                        self.on_connect(joystick.get_name())
                elif event.type == pygame.JOYDEVICEREMOVED:
                    joysticks.pop(event.instance_id, None)
                elif event.type == pygame.JOYBUTTONDOWN:
                    key = BUTTONS.get(event.button)
                    if key:
                        self.send_key(key)
                elif event.type == pygame.JOYHATMOTION:
                    key = HAT.get(tuple(event.value))
                    if key:
                        self.send_key(key)
            now = time.time()
            for joystick in joysticks.values():
                if joystick.get_numaxes() < 2:
                    continue
                x, y = joystick.get_axis(0), joystick.get_axis(1)
                key = None
                if abs(x) > DEADZONE and abs(x) >= abs(y):
                    key = 'DPAD_RIGHT' if x > 0 else 'DPAD_LEFT'
                elif abs(y) > DEADZONE:
                    key = 'DPAD_DOWN' if y > 0 else 'DPAD_UP'
                ident = joystick.get_instance_id()
                if key and now - last_axis.get(ident, 0) > REPEAT_SECONDS:
                    last_axis[ident] = now
                    self.send_key(key)
                elif not key:
                    last_axis[ident] = 0
            time.sleep(0.02)
