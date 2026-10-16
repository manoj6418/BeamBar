# Third Party Library
import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSBezelStyleRounded,
    NSButton,
    NSColor,
    NSFont,
    NSImageScaleProportionallyUpOrDown,
    NSImageView,
    NSLayoutAttributeCenterX,
    NSMakeRect,
    NSPanel,
    NSPasteboard,
    NSPasteboardTypeString,
    NSStackView,
    NSTextAlignmentCenter,
    NSTextField,
    NSUserInterfaceLayoutOrientationVertical,
    NSView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialPopover,
    NSWindowMiniaturizeButton,
    NSWindowZoomButton,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject

from qr import qr_image

WIDTH, HEIGHT = 300, 420
QR = 200
PAD = 10  # white around the code; with the code's own margin it keeps the quiet zone phones need


def label(text, size, weight=0.0, color=None, mono=False):
    field = NSTextField.labelWithString_(text)
    font = (NSFont.monospacedSystemFontOfSize_weight_(size, weight) if mono
            else NSFont.systemFontOfSize_weight_(size, weight))
    field.setFont_(font)
    field.setAlignment_(NSTextAlignmentCenter)
    field.setTextColor_(color or NSColor.labelColor())
    return field


class BeamBarPhoneQR(NSObject):
    """A small floating panel with a QR code that opens the phone remote."""

    def initWithStable_byIP_(self, stable, by_ip):
        self = objc.super(BeamBarPhoneQR, self).init()
        if self is None:
            return None
        self.stable, self.by_ip, self.showing_ip = stable, by_ip, False
        self.build()
        return self

    def build(self):
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, HEIGHT),
            NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskFullSizeContentView,
            NSBackingStoreBuffered, False,
        )
        panel.setTitle_('Phone remote')
        panel.setTitlebarAppearsTransparent_(True)
        panel.setTitleVisibility_(1)  # hidden; the panel shows its own title
        panel.setMovableByWindowBackground_(True)
        panel.setFloatingPanel_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        for button in (NSWindowMiniaturizeButton, NSWindowZoomButton):
            panel.standardWindowButton_(button).setHidden_(True)

        glass = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
        glass.setMaterial_(NSVisualEffectMaterialPopover)
        glass.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        glass.setState_(NSVisualEffectStateActive)
        panel.setContentView_(glass)

        title = label('Phone remote', 17, 0.6)
        hint = label('Scan with your phone camera', 12, 0.0, NSColor.secondaryLabelColor())

        side = QR + 2 * PAD
        card = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, side, side))
        card.setWantsLayer_(True)
        card.layer().setBackgroundColor_(NSColor.whiteColor().CGColor())
        card.layer().setCornerRadius_(16)
        self.qr_view = NSImageView.alloc().initWithFrame_(NSMakeRect(PAD, PAD, QR, QR))
        self.qr_view.setImageScaling_(NSImageScaleProportionallyUpOrDown)
        card.addSubview_(self.qr_view)
        card.setTranslatesAutoresizingMaskIntoConstraints_(False)
        card.widthAnchor().constraintEqualToConstant_(side).setActive_(True)
        card.heightAnchor().constraintEqualToConstant_(side).setActive_(True)

        self.link = label('', 13, 0.5, mono=True)
        self.link.setSelectable_(True)
        note = label('Your phone must be on the same Wi-Fi', 11, 0.0, NSColor.secondaryLabelColor())
        note.setToolTip_('Tip: add it to the Home Screen for an app-like remote.')

        self.copy_button = NSButton.buttonWithTitle_target_action_('Copy link', self, 'copyLink:')
        self.copy_button.setBezelStyle_(NSBezelStyleRounded)
        self.copy_button.setKeyEquivalent_('\r')
        self.switch_button = NSButton.buttonWithTitle_target_action_('', self, 'toggleAddress:')
        self.switch_button.setBordered_(False)
        self.switch_button.setFont_(NSFont.systemFontOfSize_(11))
        self.switch_button.setContentTintColor_(NSColor.linkColor())
        close = NSButton.buttonWithTitle_target_action_('', self, 'closePanel:')
        close.setKeyEquivalent_('\x1b')  # Esc
        close.setFrame_(NSMakeRect(0, 0, 0, 0))

        stack = NSStackView.stackViewWithViews_([title, hint, card, self.link, note, self.copy_button, self.switch_button])
        stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        stack.setAlignment_(NSLayoutAttributeCenterX)
        stack.setSpacing_(10)
        stack.setCustomSpacing_afterView_(2, title)
        stack.setCustomSpacing_afterView_(16, hint)
        stack.setCustomSpacing_afterView_(14, card)
        stack.setCustomSpacing_afterView_(4, self.link)
        stack.setCustomSpacing_afterView_(16, note)
        stack.setCustomSpacing_afterView_(2, self.copy_button)
        stack.setTranslatesAutoresizingMaskIntoConstraints_(False)
        glass.addSubview_(stack)
        glass.addSubview_(close)
        stack.centerXAnchor().constraintEqualToAnchor_(glass.centerXAnchor()).setActive_(True)
        stack.topAnchor().constraintEqualToAnchor_constant_(glass.topAnchor(), 34).setActive_(True)

        self.panel = panel
        self.refresh()
        # Fit the panel to its content with even padding at the bottom.
        stack.layoutSubtreeIfNeeded()
        panel.setContentSize_((WIDTH, 34 + stack.fittingSize().height + 18))

    def refresh(self):
        url = self.by_ip if self.showing_ip else self.stable
        self.qr_view.setImage_(qr_image(url, QR, margin=0.04))
        self.link.setStringValue_(url.replace('http://', ''))
        self.switch_button.setTitle_('Use the .local link instead' if self.showing_ip else "Phone can't open it? Use the IP link")
        self.copy_button.setTitle_('Copy link')

    def show(self):
        self.panel.center()
        NSApp.activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)

    def copyLink_(self, _):
        url = self.by_ip if self.showing_ip else self.stable
        NSPasteboard.generalPasteboard().clearContents()
        NSPasteboard.generalPasteboard().setString_forType_(url, NSPasteboardTypeString)
        self.copy_button.setTitle_('Copied ✓')

    def toggleAddress_(self, _):
        self.showing_ip = not self.showing_ip
        self.refresh()

    def closePanel_(self, _):
        self.panel.orderOut_(None)
