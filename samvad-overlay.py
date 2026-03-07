#!/usr/bin/env python3
"""
samvad-overlay.py — Minimal floating overlay UI for Samvad

Hidden by default. Appears only when recording/processing, then disappears.
Small pill at bottom-center, above the dock.

Run via: samvad --overlay  (or run-overlay.sh)
"""
from __future__ import annotations
import json
import math
import os
import subprocess
import sys
import threading
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

# States where the pill should be visible
VISIBLE_STATES = {"recording", "transcribing", "translating", "polishing", "done", "error", "perm"}


class OverlayView(NSView):
    """Custom view that draws the pill background and status text."""

    def initWithFrame_(self, frame):
        self = objc.super(OverlayView, self).initWithFrame_(frame)
        if self is None:
            return None
        self._status = "init"
        self._text = ""
        self._rec_start = 0.0
        self._tick_count = 0
        self._done_time = 0.0
        self._err_time = 0.0
        self._err_msg = ""
        self._perm_im = False
        self._perm_ax = False
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

    def tick(self):
        self._tick_count += 1

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
        self._core_proc = None
        self._core_stdin = None
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
        panel.setIgnoresMouseEvents_(False)
        panel.setMovableByWindowBackground_(True)
        panel.setCollectionBehavior_(
            AppKit.NSWindowCollectionBehaviorCanJoinAllSpaces
            | AppKit.NSWindowCollectionBehaviorStationary
            | AppKit.NSWindowCollectionBehaviorFullScreenAuxiliary
        )
        # Start hidden — alpha 0
        panel.setAlphaValue_(0.0)

        overlay = OverlayView.alloc().initWithFrame_(
            NSMakeRect(0, 0, PILL_W, PILL_H)
        )
        panel.setContentView_(overlay)
        panel.orderFrontRegardless()

        self._window = panel
        self._overlay = overlay
        self._visible = False

        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            0.1, self, "onTick:", None, True
        )

        thread = threading.Thread(target=self._run_core, daemon=True)
        thread.start()

    def _show_pill(self):
        """Fade in the pill."""
        if self._visible:
            return
        self._visible = True
        panel = self._window
        if panel is None:
            return
        ctx = NSAnimationContext.currentContext()
        ctx.setDuration_(0.2)
        panel.animator().setAlphaValue_(1.0)

    def _hide_pill(self):
        """Fade out the pill."""
        if not self._visible:
            return
        self._visible = False
        panel = self._window
        if panel is None:
            return
        ctx = NSAnimationContext.currentContext()
        ctx.setDuration_(0.3)
        panel.animator().setAlphaValue_(0.0)

    def onTick_(self, timer):
        ov = self._overlay
        if ov is None:
            return
        ov.tick()

        # Show/hide based on status
        if ov._status in VISIBLE_STATES:
            self._show_pill()
        else:
            self._hide_pill()

    def _find_uv(self):
        for p in [
            os.path.expanduser("~/.cargo/bin/uv"),
            os.path.expanduser("~/.local/bin/uv"),
            "/usr/local/bin/uv",
            "/opt/homebrew/bin/uv",
        ]:
            if os.path.isfile(p):
                return p
        return "uv"

    def _run_core(self):
        """Spawn samvad-core.py and read its JSON messages. Retry on failure."""
        dir_ = Path(__file__).parent
        uv = self._find_uv()
        args = [
            uv, "run", "--python", "3.11", "--no-project",
            "--with", "sounddevice>=0.4",
            "--with", "numpy>=1.26",
            "--with", "requests>=2.28",
            "--with", "pyobjc-framework-Cocoa>=10",
            "--with", "pyobjc-framework-Quartz>=10",
            "python", str(dir_ / "samvad-core.py"),
        ]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                proc = subprocess.Popen(
                    args,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=os.environ.copy(),
                )
            except FileNotFoundError:
                print(f"ERROR: '{uv}' not found.", file=sys.stderr, flush=True)
                time.sleep(2)
                continue

            self._core_proc = proc
            self._core_stdin = proc.stdin

            for raw in proc.stdout:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    self.performSelectorOnMainThread_withObject_waitUntilDone_(
                        "handleCoreMsg:", msg, False
                    )
                except Exception:
                    pass

            stderr_out = proc.stderr.read().decode(errors="replace").strip()
            exit_code = proc.wait()

            if exit_code == 0:
                print("Core exited cleanly.", file=sys.stderr, flush=True)
                break

            print(f"Core exited with code {exit_code} (attempt {attempt+1}/{max_retries})",
                  file=sys.stderr, flush=True)
            if stderr_out:
                print(f"Core stderr: {stderr_out[:500]}", file=sys.stderr, flush=True)

            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "handleCoreMsg:", {"type": "error", "msg": "Core crashed, retrying..."}, False
            )
            time.sleep(3)

    def handleCoreMsg_(self, msg):
        if not isinstance(msg, dict):
            return
        t = msg.get("type", "")
        ov = self._overlay
        if ov is None:
            return

        if t == "ready":
            ov._status = "idle"

        elif t == "status":
            status = msg.get("status", "")
            ov._status = status
            if status == "recording":
                ov._rec_start = time.monotonic()

        elif t == "done":
            ov._status = "done"
            ov._done_time = time.monotonic()
            ov._text = msg.get("text", "")

        elif t == "error":
            ov._status = "error"
            ov._err_msg = msg.get("msg", "unknown")
            ov._err_time = time.monotonic()

        elif t == "perm":
            ov._perm_im = bool(msg.get("im"))
            ov._perm_ax = bool(msg.get("ax"))
            if not (ov._perm_im and ov._perm_ax):
                ov._status = "perm"
            else:
                ov._status = "init"

        elif t == "amp":
            return

        elif t == "init":
            pass

        ov.setNeedsDisplay_(True)

    def quitApp_(self, _):
        NSApp.terminate_(None)

    def sendToCore_(self, msg):
        if self._core_stdin:
            try:
                self._core_stdin.write((json.dumps(msg) + "\n").encode())
                self._core_stdin.flush()
            except Exception:
                pass


def main():
    app = NSApplication.sharedApplication()
    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    app.run()


if __name__ == "__main__":
    main()
