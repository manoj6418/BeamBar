# Standard Library
import json
from pathlib import Path

# Third Party Library
from AppKit import (
    NSApplication,
    NSMakeRect,
    NSMinYEdge,
    NSPopover,
    NSPopoverBehaviorTransient,
    NSURL,
    NSViewController,
    NSViewHeightSizable,
    NSViewWidthSizable,
)
from WebKit import WKWebView, WKWebViewConfiguration

from pad import Bridge
from paths import RESOURCES

HTML = RESOURCES / 'center.html'
WIDTH = 340


class ControlCenter:
    """The popover that opens from the menu bar icon: status, now playing, volume, apps and actions."""

    def __init__(self, on_message):
        self.bridge = Bridge.alloc().init()
        self.bridge.on_message = on_message
        config = WKWebViewConfiguration.alloc().init()
        config.userContentController().addScriptMessageHandler_name_(self.bridge, 'remote')
        self.webview = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, WIDTH, 520), config)
        self.webview.setValue_forKey_(False, 'drawsBackground')
        self.webview.setAutoresizingMask_(NSViewWidthSizable | NSViewHeightSizable)
        self.webview.loadFileURL_allowingReadAccessToURL_(
            NSURL.fileURLWithPath_(str(HTML)), NSURL.fileURLWithPath_(str(HTML.parent))
        )
        controller = NSViewController.alloc().init()
        controller.setView_(self.webview)
        self.popover = NSPopover.alloc().init()
        self.popover.setContentViewController_(controller)
        self.popover.setContentSize_((WIDTH, 520))
        self.popover.setBehavior_(NSPopoverBehaviorTransient)
        self.popover.setAnimates_(True)

    def is_shown(self):
        return self.popover.isShown()

    def toggle(self, anchor):
        if self.popover.isShown():
            self.close()
            return
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self.popover.showRelativeToRect_ofView_preferredEdge_(anchor.bounds(), anchor, NSMinYEdge)
        self.popover.contentViewController().view().window().makeKeyWindow()

    def close(self):
        if self.popover.isShown():
            self.popover.performClose_(None)

    def resize_to(self, height):
        if height > 60 and abs(self.popover.contentSize().height - height) >= 1:
            self.popover.setContentSize_((WIDTH, height))

    def push_status(self, status):
        script = f'window.remote && window.remote.setStatus({json.dumps(status)})'
        self.webview.evaluateJavaScript_completionHandler_(script, None)
