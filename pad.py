# Standard Library
import json
from pathlib import Path

# Third Party Library
import objc
from AppKit import (
    NSApplication,
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSEdgeInsetsMake,
    NSEventTypeKeyDown,
    NSFloatingWindowLevel,
    NSImage,
    NSImageResizingModeStretch,
    NSPanel,
    NSViewHeightSizable,
    NSViewWidthSizable,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialUnderWindowBackground,
    NSVisualEffectStateActive,
    NSVisualEffectView,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSMakeRect, NSObject, NSURL
from WebKit import WKWebView, WKWebViewConfiguration

WIDTH = 300
HEIGHT = 632
RADIUS = 28
ESCAPE_KEYCODE = 53
HTML = Path(__file__).with_name('pad.html')


class PadPanel(NSPanel):
    def canBecomeKeyWindow(self):
        return True

    def canBecomeMainWindow(self):
        return False

    def sendEvent_(self, event):
        if event.type() == NSEventTypeKeyDown and event.keyCode() == ESCAPE_KEYCODE:
            script = "window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))"
            self.webview.evaluateJavaScript_completionHandler_(script, None)
            return
        objc.super(PadPanel, self).sendEvent_(event)

    def push_status(self, status):
        script = f'window.remote && window.remote.setStatus({json.dumps(status)})'
        self.webview.evaluateJavaScript_completionHandler_(script, None)
        if not self.shadow_ready:
            self.shadow_ready = True
            self.invalidateShadow()

    def resize_to(self, height):
        if height < 60:
            return
        frame = self.frame()
        if abs(frame.size.height - height) < 1:
            return
        top = frame.origin.y + frame.size.height
        self.setFrame_display_animate_(NSMakeRect(frame.origin.x, top - height, frame.size.width, height), True, True)

    def begin_drag(self):
        event = NSApplication.sharedApplication().currentEvent()
        if event is not None:
            self.performWindowDragWithEvent_(event)


class Bridge(NSObject, protocols=[objc.protocolNamed('WKScriptMessageHandler')]):
    def userContentController_didReceiveScriptMessage_(self, controller, message):
        body = message.body()
        if isinstance(body, dict) or hasattr(body, 'keys'):
            self.on_message({str(k): body[k] for k in body.keys()})


def rounded_mask(radius):
    size = radius * 2 + 1

    def draw(rect):
        NSColor.blackColor().set()
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius).fill()
        return True

    image = NSImage.imageWithSize_flipped_drawingHandler_((size, size), False, draw)
    image.setCapInsets_(NSEdgeInsetsMake(radius, radius, radius, radius))
    image.setResizingMode_(NSImageResizingModeStretch)
    return image


def build_pad(on_message):
    style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
    panel = PadPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, WIDTH, HEIGHT), style, NSBackingStoreBuffered, False
    )
    panel.setTitle_('BeamBar Remote')
    panel.setLevel_(NSFloatingWindowLevel)
    panel.setOpaque_(False)
    panel.setBackgroundColor_(NSColor.clearColor())
    panel.setHasShadow_(True)
    panel.setHidesOnDeactivate_(False)
    panel.setReleasedWhenClosed_(False)
    panel.setMovableByWindowBackground_(True)
    panel.shadow_ready = False

    effect = NSVisualEffectView.alloc().initWithFrame_(NSMakeRect(0, 0, WIDTH, HEIGHT))
    effect.setMaterial_(NSVisualEffectMaterialUnderWindowBackground)
    effect.setBlendingMode_(NSVisualEffectBlendingModeBehindWindow)
    effect.setState_(NSVisualEffectStateActive)
    effect.setMaskImage_(rounded_mask(RADIUS))
    panel.setContentView_(effect)

    bridge = Bridge.alloc().init()
    bridge.on_message = on_message
    config = WKWebViewConfiguration.alloc().init()
    config.userContentController().addScriptMessageHandler_name_(bridge, 'remote')
    webview = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, WIDTH, HEIGHT), config)
    webview.setValue_forKey_(False, 'drawsBackground')
    webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
    webview.loadFileURL_allowingReadAccessToURL_(
        NSURL.fileURLWithPath_(str(HTML)), NSURL.fileURLWithPath_(str(HTML.parent))
    )
    effect.addSubview_(webview)

    panel.webview = webview
    panel.bridge = bridge
    panel.center()
    panel.setFrameAutosaveName_('XgimiRemoteGlass')
    return panel
