# Third Party Library
import objc
from AppKit import (
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageSymbolConfiguration,
    NSImageView,
    NSMakeRect,
    NSSlider,
    NSTextField,
    NSView,
)
from Foundation import NSObject

WIDTH = 280


def symbol(name, size=15, weight=0.0):
    image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name, None)
    if image is None:
        return None
    config = NSImageSymbolConfiguration.configurationWithPointSize_weight_(size, weight)
    return image.imageWithSymbolConfiguration_(config)


class MenuTarget(NSObject):
    """Bridges button and slider actions in the menu to Python callables."""

    def initWithHandler_(self, handler):
        self = objc.super(MenuTarget, self).init()
        if self is None:
            return None
        self.handler = handler
        return self

    def fire_(self, sender):
        self.handler(sender)


class StatusHeader:
    """Top of the menu: a status dot, the device name and what's on."""

    def __init__(self):
        self.view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 46))
        self.dot = NSView.alloc().initWithFrame_(NSMakeRect(16, 19, 9, 9))
        self.dot.setWantsLayer_(True)
        self.dot.layer().setCornerRadius_(4.5)
        self.name = NSTextField.labelWithString_('BeamBar')
        self.name.setFont_(NSFont.systemFontOfSize_weight_(13.5, 0.6))
        self.name.setFrame_(NSMakeRect(34, 23, WIDTH - 50, 18))
        self.sub = NSTextField.labelWithString_('Connecting…')
        self.sub.setFont_(NSFont.systemFontOfSize_(11.5))
        self.sub.setTextColor_(NSColor.secondaryLabelColor())
        self.sub.setFrame_(NSMakeRect(34, 6, WIDTH - 50, 16))
        for view in (self.dot, self.name, self.sub):
            self.view.addSubview_(view)
        self.update('BeamBar', 'Connecting…', 'connecting')

    def update(self, name, sub, state):
        colors = {'connected': NSColor.systemGreenColor(), 'connecting': NSColor.systemYellowColor()}
        self.dot.layer().setBackgroundColor_(colors.get(state, NSColor.systemOrangeColor()).CGColor())
        if self.name.stringValue() != name:
            self.name.setStringValue_(name)
        if self.sub.stringValue() != sub:
            self.sub.setStringValue_(sub)


class ControlsRow:
    """Previous, play/pause, next, mute and home as buttons spread evenly across the menu."""

    def __init__(self, buttons):
        self.targets = []
        self.view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 36))
        margin, slot = 14, (WIDTH - 28) / len(buttons)
        for i, (name, tip, handler) in enumerate(buttons):
            target = MenuTarget.alloc().initWithHandler_(lambda _, h=handler: h())
            self.targets.append(target)
            button = NSButton.buttonWithImage_target_action_(symbol(name, 15, 0.2), target, 'fire:')
            button.setBordered_(False)
            button.setToolTip_(tip)
            button.setContentTintColor_(NSColor.labelColor())
            button.setFrame_(NSMakeRect(margin + i * slot, 3, slot, 30))
            self.view.addSubview_(button)


class VolumeRow:
    """A volume slider; the TV is set when you let go."""

    def __init__(self, on_change):
        self.view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 34))
        low = NSImageView.imageViewWithImage_(symbol('speaker.fill', 12))
        low.setFrame_(NSMakeRect(16, 9, 16, 16))
        low.setContentTintColor_(NSColor.secondaryLabelColor())
        high = NSImageView.imageViewWithImage_(symbol('speaker.wave.3.fill', 12))
        high.setFrame_(NSMakeRect(WIDTH - 66, 9, 22, 16))
        high.setContentTintColor_(NSColor.secondaryLabelColor())
        self.target = MenuTarget.alloc().initWithHandler_(self.changed)
        self.slider = NSSlider.sliderWithValue_minValue_maxValue_target_action_(30, 0, 100, self.target, 'fire:')
        self.slider.setFrame_(NSMakeRect(38, 7, WIDTH - 110, 20))
        self.slider.setContinuous_(False)
        self.level = NSTextField.labelWithString_('–')
        self.level.setFont_(NSFont.monospacedDigitSystemFontOfSize_weight_(11.5, 0.4))
        self.level.setTextColor_(NSColor.secondaryLabelColor())
        self.level.setFrame_(NSMakeRect(WIDTH - 40, 9, 30, 16))
        for view in (low, self.slider, high, self.level):
            self.view.addSubview_(view)
        self.on_change = on_change

    def changed(self, slider):
        value = int(round(slider.doubleValue()))
        self.level.setStringValue_(str(value))
        self.on_change(value)

    def update(self, volume):
        if volume is None:
            self.level.setStringValue_('–')
            return
        if int(self.slider.doubleValue()) != int(volume):
            self.slider.setDoubleValue_(volume)
        self.level.setStringValue_(str(int(volume)))
