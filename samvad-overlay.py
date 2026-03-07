#!/usr/bin/env python3
"""
samvad-overlay.py — Floating indicator for Samvad

Runs alongside the terminal UI. Reads status from /tmp/.samvad_state.json
(written by samvad-ui.py). Hidden when idle, appears when listening/processing.

Launched automatically by daemon.sh — no need to run manually.
"""
from __future__ import annotations
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

import AppKit
from AppKit import (
    NSApplication,
    NSApp,
    NSPanel,
    NSView,
    NSColor,
    NSFont,
    NSAttributedString,
    NSTimer,
    NSScreen,
    NSMakeRect,
    NSMakePoint,
    NSBezierPath,
    NSMutableDictionary,
    NSForegroundColorAttributeName,
    NSFontAttributeName,
    NSApplicationActivationPolicyAccessory,
    NSAnimationContext,
)
from Foundation import NSObject
import objc

# ── State file ────────────────────────────────────────────────────────────────
STATE_FILE = Path(tempfile.gettempdir()) / ".samvad_state.json"

# ── Layout ────────────────────────────────────────────────────────────────────
PILL_W = 160
PILL_H = 36
PILL_RADIUS = 18
MARGIN_BOTTOM = 120  # above the dock

# ── Colors ────────────────────────────────────────────────────────────────────
def rgba(r, g, b, a=1.0):
    return NSColor.colorWithCalibratedRed_green_blue_alpha_(r/255, g/255, b/255, a)

COL_BG       = rgba(18, 18, 18, 0.85)
COL_BG_REC   = rgba(40, 12, 12, 0.9)
COL_BG_WORK  = rgba(12, 30, 28, 0.9)
COL_BG_DONE  = rgba(12, 35, 12, 0.9)
COL_BG_ERR   = rgba(40, 12, 12, 0.9)
COL_BG_PERM  = rgba(35, 28, 8, 0.9)
COL_TEAL     = rgba(63, 184, 169)
COL_RED      = rgba(224, 85, 85)
COL_GREEN    = rgba(78, 201, 78)
COL_GOLD     = rgba(212, 165, 32)
COL_MUTED    = rgba(120, 120, 120)
COL_WHITE    = rgba(230, 230, 230)
COL_DIM      = rgba(80, 80, 80)

SPIN = ["\u280B","\u2819","\u2839","\u2838","\u283C","\u2834","\u2826","\u2827","\u2807","\u280F"]

# States where the pill is visible
VISIBLE_STATES = {"recording", "transcribing", "translating", "polishing", "done", "error", "perm"}


class OverlayView(NSView):

    def initWithFrame_(self, frame):
        self = objc.super(OverlayView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._status = "idle"
        self._text = ""
        self._err_msg = ""
        self._rec_start = 0.0
        self._tick_count = 0
        self._done_time = 0.0
        self._err_time = 0.0
        self._perm_im = False
        self._perm_ax = False
        self._prev_status = "idle"
        return self

    def isFlipped(self):
        return False

    def drawRect_(self, rect):
        bg = {
            "recording":    COL_BG_REC,
            "transcribing": COL_BG_WORK,
            "translating":  COL_BG_WORK,
            "polishing":    COL_BG_WORK,
            "done":         COL_BG_DONE,
            "error":        COL_BG_ERR,
            "perm":         COL_BG_PERM,
        }.get(self._status, COL_BG)

        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            self.bounds(), PILL_RADIUS, PILL_RADIUS
        )
        bg.setFill()
        path.fill()

        border_col = {
            "recording":    COL_RED,
            "transcribing": COL_TEAL,
            "translating":  COL_TEAL,
            "polishing":    COL_TEAL,
            "done":         COL_GREEN,
            "error":        COL_RED,
            "perm":         COL_GOLD,
        }.get(self._status, COL_DIM)
        border_col.colorWithAlphaComponent_(0.5).setStroke()
        path.setLineWidth_(1.0)
        path.stroke()

        icon, label, icon_col = self._get_display()

        icon_attrs = NSMutableDictionary.dictionary()
        icon_attrs[NSFontAttributeName] = NSFont.systemFontOfSize_(14)
        icon_attrs[NSForegroundColorAttributeName] = icon_col
        icon_str = NSAttributedString.alloc().initWithString_attributes_(icon, icon_attrs)
        icon_str.drawAtPoint_(NSMakePoint(12, 9))

        label_attrs = NSMutableDictionary.dictionary()
        label_attrs[NSFontAttributeName] = NSFont.systemFontOfSize_weight_(12, 0.2)
        label_attrs[NSForegroundColorAttributeName] = COL_WHITE
        label_str = NSAttributedString.alloc().initWithString_attributes_(label, label_attrs)
        label_str.drawAtPoint_(NSMakePoint(32, 10))

    def _get_display(self):
        spin = SPIN[self._tick_count % len(SPIN)]

        if self._status == "recording":
            elapsed = int(time.monotonic() - self._rec_start)
            mm, ss = divmod(elapsed, 60)
            pulse = 0.5 + 0.5 * math.sin(self._tick_count * 0.5)
            col = COL_RED.colorWithAlphaComponent_(0.5 + 0.5 * pulse)
            return ("\u25CF", f"Listening  {mm:02d}:{ss:02d}", col)

        elif self._status in ("transcribing", "translating", "polishing"):
            labels = {
                "transcribing": "Transcribing...",
                "translating":  "Translating...",
                "polishing":    "Polishing...",
            }
            return (spin, labels.get(self._status, "Processing..."), COL_TEAL)

        elif self._status == "done":
            preview = self._text[:18] + ("..." if len(self._text) > 18 else "")
            return ("\u2713", preview or "Pasted", COL_GREEN)

        elif self._status == "error":
            short = self._err_msg[:20] if self._err_msg else "Error"
            return ("\u2717", short, COL_RED)

        elif self._status == "perm":
            if not self._perm_im:
                return ("\u2699", "Grant Input Mon.", COL_GOLD)
            elif not self._perm_ax:
                return ("\u2699", "Grant Accessibility", COL_GOLD)
            else:
                return ("\u2713", "Permissions OK", COL_GREEN)

        else:
            return ("\u25CC", "Samvad", COL_TEAL)

    def readState(self):
        """Read status from the shared state file."""
        try:
            if not STATE_FILE.exists():
                return
            data = json.loads(STATE_FILE.read_text())
            new_status = data.get("status", "idle")

            # Track transitions
            if new_status != self._prev_status:
                if new_status == "recording":
                    self._rec_start = time.monotonic()
                elif new_status == "done":
                    self._done_time = time.monotonic()
                    self._text = data.get("text", "")
                elif new_status == "error":
                    self._err_time = time.monotonic()
                    self._err_msg = data.get("msg", "")
                elif new_status == "perm":
                    self._perm_im = data.get("im", False)
                    self._perm_ax = data.get("ax", False)
                self._prev_status = new_status

            self._status = new_status
        except Exception:
            pass

    def tick(self):
        self._tick_count += 1
        self.readState()

        # Auto-hide done after 3s
        if self._status == "done" and time.monotonic() - self._done_time > 3:
            self._status = "idle"

        # Auto-hide error after 4s
        if self._status == "error" and time.monotonic() - self._err_time > 4:
            self._status = "idle"

        self._resize_pill()
        self.setNeedsDisplay_(True)

    def _resize_pill(self):
        _, label, _ = self._get_display()
        text_w = len(label) * 8 + 48
        new_w = max(PILL_W, min(300, int(text_w)))
        window = self.window()
        if window is None:
            return
        frame = window.frame()
        if abs(frame.size.width - new_w) > 2:
            screen = NSScreen.mainScreen().frame()
            x = (screen.size.width - new_w) / 2
            window.setFrame_display_(NSMakeRect(x, MARGIN_BOTTOM, new_w, PILL_H), True)
            self.setFrame_(NSMakeRect(0, 0, new_w, PILL_H))


class AppDelegate(NSObject):
    def init(self):
        self = objc.super(AppDelegate, self).init()
        self._window = None
        self._overlay = None
        self._visible = False
        return self

    def applicationDidFinishLaunching_(self, notification):
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        screen = NSScreen.mainScreen().frame()
        x = (screen.size.width - PILL_W) / 2

        style = AppKit.NSWindowStyleMaskBorderless
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, MARGIN_BOTTOM, PILL_W, PILL_H),
            style | AppKit.NSWindowStyleMaskNonactivatingPanel,
            AppKit.NSBackingStoreBuffered,
            False,
        )
        panel.setLevel_(AppKit.NSFloatingWindowLevel)
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        # Start hidden
        panel.setAlphaValue_(0.0)

        overlay = OverlayView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PILL_W, PILL_H)
        )
        panel.setContentView_(overlay)
        panel.orderFrontRegardless()

        self._window = panel
        self._overlay = overlay
        self._visible = False

        # Poll state file at 10fps
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.1, self, "onTick:", None, True
        )

    def onTick_(self, timer):
        ov = self._overlay
        if ov is None:
            return
        ov.tick()

        if ov._status in VISIBLE_STATES:
            self._show()
        else:
            self._hide()

    def _show(self):
        if self._visible:
            return
        self._visible = True
        panel = self._window
        if panel is None:
            return
        ctx = NSAnimationContext.currentContext()
        ctx.setDuration_(0.15)
        panel.animator().setAlphaValue_(1.0)

    def _hide(self):
        if not self._visible:
            return
        self._visible = False
        panel = self._window
        if panel is None:
            return
        ctx = NSAnimationContext.currentContext()
        ctx.setDuration_(0.25)
        panel.animator().setAlphaValue_(0.0)


def main():
    # Clean up stale state on start
    try:
        STATE_FILE.write_text(json.dumps({"status": "idle"}))
    except Exception:
        pass
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
