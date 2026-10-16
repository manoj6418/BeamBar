# Third Party Library
import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFont,
    NSImageView,
    NSLayoutAttributeCenterX,
    NSLayoutAttributeCenterY,
    NSMakeRect,
    NSPanel,
    NSStackView,
    NSTextAlignmentCenter,
    NSTextField,
    NSTextFieldRoundedBezel,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSUserInterfaceLayoutOrientationVertical,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialPopover,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowMiniaturizeButton,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskTitled,
    NSWindowZoomButton,
)
from Foundation import NSObject

WIDTH = 340
FIELD = 292


class BeamBarPrompt(NSObject):
    """A small modal panel asking for one line of text: icon, title, hint, field, Cancel and an action."""

    def initWithTitle_message_default_action_placeholder_(self, title, message, default, action, placeholder):
        self = objc.super(BeamBarPrompt, self).init()
        if self is None:
            return None
        self.result = None
        self.build(title, message, default or '', action or 'OK', placeholder or '')
        return self

    @objc.python_method
    def build(self, title, message, default, action, placeholder):
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, 260),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskFullSizeContentView,
            NSBackingStoreBuffered, False,
        )
        panel.setTitle_(title)
        panel.setTitlebarAppearsTransparent_(True)
        panel.setTitleVisibility_(1)
        panel.setMovableByWindowBackground_(True)
        panel.setReleasedWhenClosed_(False)
        panel.setDelegate_(self)
        for button in (NSWindowMiniaturizeButton, NSWindowZoomButton):
            panel.standardWindowButton_(button).setHidden_(True)

        glass = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 260))
        glass.setMaterial_(NSVisualEffectMaterialPopover)
        glass.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        glass.setState_(NSVisualEffectStateActive)
        panel.setContentView_(glass)

        icon = NSImageView.imageViewWithImage_(NSApp.applicationIconImage())
        icon.setTranslatesAutoresizingMaskIntoConstraints_(False)
        icon.widthAnchor().constraintEqualToConstant_(52).setActive_(True)
        icon.heightAnchor().constraintEqualToConstant_(52).setActive_(True)

        heading = NSTextField.labelWithString_(title)
        heading.setFont_(NSFont.systemFontOfSize_weight_(15, 0.6))
        heading.setAlignment_(NSTextAlignmentCenter)

        hint = NSTextField.wrappingLabelWithString_(message)
        hint.setFont_(NSFont.systemFontOfSize_(12))
        hint.setTextColor_(NSColor.secondaryLabelColor())
        hint.setAlignment_(NSTextAlignmentCenter)
        hint.setPreferredMaxLayoutWidth_(FIELD)

        self.field = NSTextField.textFieldWithString_(default)
        self.field.setBezelStyle_(NSTextFieldRoundedBezel)
        self.field.setFont_(NSFont.systemFontOfSize_(14))
        self.field.setPlaceholderString_(placeholder)
        self.field.setTranslatesAutoresizingMaskIntoConstraints_(False)
        self.field.widthAnchor().constraintEqualToConstant_(FIELD).setActive_(True)
        self.field.heightAnchor().constraintEqualToConstant_(30).setActive_(True)

        cancel = NSButton.buttonWithTitle_target_action_('Cancel', self, 'cancel:')
        cancel.setBezelStyle_(NSBezelStyleRounded)
        cancel.setKeyEquivalent_('\x1b')
        primary = NSButton.buttonWithTitle_target_action_(action, self, 'confirm:')
        primary.setBezelStyle_(NSBezelStyleRounded)
        primary.setKeyEquivalent_('\r')
        for button in (cancel, primary):
            button.setTranslatesAutoresizingMaskIntoConstraints_(False)
            button.widthAnchor().constraintEqualToConstant_((FIELD - 10) / 2).setActive_(True)
        buttons = NSStackView.stackViewWithViews_([cancel, primary])
        buttons.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        buttons.setAlignment_(NSLayoutAttributeCenterY)
        buttons.setSpacing_(10)

        stack = NSStackView.stackViewWithViews_([icon, heading, hint, self.field, buttons])
        stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        stack.setAlignment_(NSLayoutAttributeCenterX)
        stack.setSpacing_(8)
        stack.setCustomSpacing_afterView_(10, icon)
        stack.setCustomSpacing_afterView_(4, heading)
        stack.setCustomSpacing_afterView_(14, hint)
        stack.setCustomSpacing_afterView_(16, self.field)
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        glass.addSubview_(stack)
        stack.centerXAnchor().constraintEqualToAnchor_(glass.centerXAnchor()).setActive_(True)
        stack.topAnchor().constraintEqualToAnchor_constant_(glass.topAnchor(), 30).setActive_(True)
        stack.layoutSubtreeIfNeeded()
        panel.setContentSize_((WIDTH, 30 + stack.fittingSize().height + 20))
        self.panel = panel

    @objc.python_method
    def run(self):
        """Shows the panel modally; returns the text, or None if cancelled."""
        self.panel.center()
        NSApp.activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)
        self.panel.makeFirstResponder_(self.field)
        self.field.selectText_(None)
        NSApp.runModalForWindow_(self.panel)
        self.panel.orderOut_(None)
        return self.result

    def confirm_(self, _):
        self.result = self.field.stringValue()
        NSApp.stopModal()

    def cancel_(self, _):
        self.result = None
        NSApp.stopModal()

    def windowShouldClose_(self, _):
        self.cancel_(None)
        return True


def ask(title, message, default='', action='OK', placeholder=''):
    return BeamBarPrompt.alloc().initWithTitle_message_default_action_placeholder_(
        title, message, default, action, placeholder
    ).run()
