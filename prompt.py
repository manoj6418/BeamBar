# Standard Library
import json

# Third Party Library
import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSPanel,
    NSURL,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialPopover,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowCloseButton,
    NSWindowMiniaturizeButton,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskTitled,
    NSWindowZoomButton,
)
from Foundation import NSObject
from WebKit import WKUserScript, WKWebView, WKWebViewConfiguration

from pad import Bridge
from paths import RESOURCES

HTML = RESOURCES / 'prompt.html'
WIDTH = 380
DOCUMENT_START = 0  # WKUserScriptInjectionTimeAtDocumentStart


class BeamBarPrompt(NSObject):
    """A small modal panel asking for one line of text, drawn by prompt.html in the control center's style."""

    def initWithOptions_(self, options):
        self = objc.super(BeamBarPrompt, self).init()
        if self is None:
            return None
        self.result = None
        self.build(options)
        return self

    @objc.python_method
    def build(self, options):
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, 200),
            NSWindowStyleMaskTitled | NSWindowStyleMaskFullSizeContentView,
            NSBackingStoreBuffered, False,
        )
        panel.setTitle_(options['title'])
        panel.setTitlebarAppearsTransparent_(True)
        panel.setTitleVisibility_(1)
        panel.setMovableByWindowBackground_(True)
        panel.setReleasedWhenClosed_(False)
        for kind in (NSWindowCloseButton, NSWindowMiniaturizeButton, NSWindowZoomButton):
            button = panel.standardWindowButton_(kind)
            if button is not None:
                button.setHidden_(True)

        glass = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 200))
        glass.setMaterial_(NSVisualEffectMaterialPopover)
        glass.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        glass.setState_(NSVisualEffectStateActive)
        panel.setContentView_(glass)

        self.bridge = Bridge.alloc().init()
        self.bridge.on_message = self.on_message
        config = WKWebViewConfiguration.alloc().init()
        controller = config.userContentController()
        controller.addScriptMessageHandler_name_(self.bridge, 'remote')
        setup = f'window.PROMPT = {json.dumps(options)};'
        controller.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(setup, DOCUMENT_START, True)
        )
        self.webview = WKWebView.alloc().initWithFrame_configuration_(glass.bounds(), config)
        self.webview.setValue_forKey_(False, 'drawsBackground')
        self.webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        glass.addSubview_(self.webview)
        self.webview.loadFileURL_allowingReadAccessToURL_(
            NSURL.fileURLWithPath_(str(HTML)), NSURL.fileURLWithPath_(str(HTML.parent))
        )
        self.panel = panel

    @objc.python_method
    def on_message(self, msg):
        kind = msg.get('type')
        if kind in ('ready', 'size'):
            height = float(msg.get('h') or 0)
            if height > 60 and abs(self.panel.contentView().frame().size.height - height) >= 1:
                frame = self.panel.frame()
                top = frame.origin.y + frame.size.height
                self.panel.setContentSize_((WIDTH, height))
                self.panel.setFrameTopLeftPoint_((frame.origin.x, top))
            if kind == 'ready':
                self.panel.center()
                self.panel.setAlphaValue_(1)
                self.panel.makeFirstResponder_(self.webview)
        elif kind == 'done':
            self.result = str(msg.get('value') or '')
            NSApp.stopModal()
        elif kind == 'cancel':
            self.result = None
            NSApp.stopModal()

    @objc.python_method
    def run(self):
        """Shows the panel modally; returns the text, or None if cancelled."""
        self.panel.setAlphaValue_(0)  # shown once the page has laid out, so it never flashes empty
        self.panel.center()
        NSApp.activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)
        NSApp.runModalForWindow_(self.panel)
        self.panel.orderOut_(None)
        self.webview.configuration().userContentController().removeScriptMessageHandlerForName_('remote')
        return self.result


def ask(title, message, default='', action='OK', placeholder='', kind='text', suggestion=''):
    """kind: text, name, url, search, number (0-100) or code (6-character pairing code)."""
    options = {
        'title': title, 'message': message, 'value': default or '', 'action': action or 'OK',
        'placeholder': placeholder or '', 'kind': kind, 'suggestion': suggestion or '',
    }
    return BeamBarPrompt.alloc().initWithOptions_(options).run()
