# Standard Library
import base64
import json

# Third Party Library
import objc
from AppKit import (
    NSApp,
    NSBackingStoreBuffered,
    NSMakeRect,
    NSPanel,
    NSPasteboard,
    NSPasteboardTypeString,
    NSRunLoop,
    NSRunLoopCommonModes,
    NSTimer,
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
from qr import png_bytes, qr_image

HTML = RESOURCES / 'qr.html'
WIDTH = 320
DOCUMENT_START = 0  # WKUserScriptInjectionTimeAtDocumentStart


def qr_png(url):
    # High error correction so the logo in the middle never makes the code unreadable; 2x for Retina.
    return base64.b64encode(png_bytes(qr_image(url, 400, margin=0, level='H'))).decode()


class BeamBarPhoneQR(NSObject):
    """A small floating panel with a QR code that opens the phone remote, drawn by qr.html."""

    def initWithStable_byIP_(self, stable, by_ip):
        self = objc.super(BeamBarPhoneQR, self).init()
        if self is None:
            return None
        self.phones = None  # optional callable: how many phones are connected right now
        self.timer = None
        self.build({'name': {'url': stable, 'png': qr_png(stable)}, 'ip': {'url': by_ip, 'png': qr_png(by_ip)}})
        return self

    @objc.python_method
    def build(self, codes):
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, WIDTH, 480),
            NSWindowStyleMaskTitled | NSWindowStyleMaskFullSizeContentView,
            NSBackingStoreBuffered, False,
        )
        panel.setTitle_('Phone remote')
        panel.setTitlebarAppearsTransparent_(True)
        panel.setTitleVisibility_(1)  # hidden; the page shows its own title
        panel.setMovableByWindowBackground_(True)
        panel.setFloatingPanel_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setReleasedWhenClosed_(False)
        for kind in (NSWindowCloseButton, NSWindowMiniaturizeButton, NSWindowZoomButton):
            button = panel.standardWindowButton_(kind)
            if button is not None:
                button.setHidden_(True)

        glass = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, 480))
        glass.setMaterial_(NSVisualEffectMaterialPopover)
        glass.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
        glass.setState_(NSVisualEffectStateActive)
        panel.setContentView_(glass)

        self.bridge = Bridge.alloc().init()
        self.bridge.on_message = self.on_message
        config = WKWebViewConfiguration.alloc().init()
        controller = config.userContentController()
        controller.addScriptMessageHandler_name_(self.bridge, 'remote')
        controller.addUserScript_(
            WKUserScript.alloc().initWithSource_injectionTime_forMainFrameOnly_(
                f'window.QR = {json.dumps(codes)};', DOCUMENT_START, True
            )
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
        if kind == 'ready':
            height = float(msg.get('h') or 0)
            if height > 60:
                self.panel.setContentSize_((WIDTH, height))
            self.panel.center()
            self.panel.setAlphaValue_(1)
            self.panel.makeFirstResponder_(self.webview)
            self.update_phones(None)
        elif kind == 'copy':
            NSPasteboard.generalPasteboard().clearContents()
            NSPasteboard.generalPasteboard().setString_forType_(str(msg.get('url', '')), NSPasteboardTypeString)
        elif kind == 'close':
            self.close()

    @objc.python_method
    def update_phones(self, _):
        if self.phones is not None:
            self.webview.evaluateJavaScript_completionHandler_(f'window.qr && window.qr.setPhones({int(self.phones())})', None)

    def is_shown(self):
        return self.panel.isVisible()

    def show(self):
        if not self.panel.isVisible():
            self.panel.setAlphaValue_(0)  # revealed once the page has laid out
            self.panel.center()
        NSApp.activateIgnoringOtherApps_(True)
        self.panel.makeKeyAndOrderFront_(None)
        if self.timer is None:
            self.timer = NSTimer.timerWithTimeInterval_repeats_block_(1.0, True, self.update_phones)
            NSRunLoop.currentRunLoop().addTimer_forMode_(self.timer, NSRunLoopCommonModes)

    def close(self):
        if self.timer is not None:
            self.timer.invalidate()
            self.timer = None
        self.panel.orderOut_(None)
