#!/usr/bin/env python3
"""
samvad-overlay-linux.py — Floating indicator for Samvad (Linux/GTK3)

Equivalent of samvad-overlay.py (macOS) but using GTK3 + Cairo.
Works on both X11 and Wayland.

Reads status from /tmp/.samvad_state.json (written by samvad-ui.py).
Hidden when idle, appears when listening/processing.

Launched automatically by daemon.sh — no need to run manually.
"""
from __future__ import annotations
import json
import math
import os
import tempfile
import time
from pathlib import Path

import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gtk, Gdk, GLib
import cairo

# ── Detect display server ────────────────────────────────────────────────────
_SESSION = os.environ.get("XDG_SESSION_TYPE", "").lower()
_IS_WAYLAND = _SESSION == "wayland" or bool(os.environ.get("WAYLAND_DISPLAY"))

# ── Try gtk-layer-shell for proper Wayland overlay support ───────────────────
_HAS_LAYER_SHELL = False
if _IS_WAYLAND:
    try:
        gi.require_version("GtkLayerShell", "0.1")
        from gi.repository import GtkLayerShell
        _HAS_LAYER_SHELL = True
    except (ValueError, ImportError):
        pass

# ── State file ────────────────────────────────────────────────────────────────
STATE_FILE = Path(tempfile.gettempdir()) / ".samvad_state.json"

# ── Layout ────────────────────────────────────────────────────────────────────
PILL_W = 160
PILL_H = 36
PILL_RADIUS = 18
MARGIN_BOTTOM = 120

# ── Colors (r, g, b, a) ──────────────────────────────────────────────────────
COL_BG       = (18/255, 18/255, 18/255, 0.85)
COL_BG_REC   = (40/255, 12/255, 12/255, 0.9)
COL_BG_WORK  = (12/255, 30/255, 28/255, 0.9)
COL_BG_DONE  = (12/255, 35/255, 12/255, 0.9)
COL_BG_ERR   = (40/255, 12/255, 12/255, 0.9)
COL_BG_PERM  = (35/255, 28/255, 8/255, 0.9)
COL_TEAL     = (63/255, 184/255, 169/255, 1.0)
COL_RED      = (224/255, 85/255, 85/255, 1.0)
COL_GREEN    = (78/255, 201/255, 78/255, 1.0)
COL_GOLD     = (212/255, 165/255, 32/255, 1.0)
COL_WHITE    = (230/255, 230/255, 230/255, 1.0)
COL_DIM      = (80/255, 80/255, 80/255, 1.0)

SPIN = ["\u280B","\u2819","\u2839","\u2838","\u283C","\u2834","\u2826","\u2827","\u2807","\u280F"]
VISIBLE_STATES = {"recording", "transcribing", "translating", "polishing", "done", "error", "perm"}


def _rounded_rect(cr, x, y, w, h, r):
    """Draw a rounded rectangle path."""
    cr.new_sub_path()
    cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cr.close_path()


class OverlayWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_resizable(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_title("samvad-overlay")
        self.stick()  # show on all workspaces

        # Transparent background
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.set_default_size(PILL_W, PILL_H)

        # Set up Wayland layer shell if available
        if _HAS_LAYER_SHELL and _IS_WAYLAND:
            GtkLayerShell.init_for_window(self)
            GtkLayerShell.set_layer(self, GtkLayerShell.Layer.OVERLAY)
            GtkLayerShell.set_anchor(self, GtkLayerShell.Edge.BOTTOM, True)
            GtkLayerShell.set_margin(self, GtkLayerShell.Edge.BOTTOM, MARGIN_BOTTOM)
            GtkLayerShell.set_keyboard_mode(self, GtkLayerShell.KeyboardMode.NONE)
        else:
            # X11 or Wayland without layer-shell: use keep-above + type hint
            self.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
            self.set_keep_above(True)

        # State
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
        self._visible = False
        self._current_w = PILL_W

        self.connect("draw", self._on_draw)

        # Position at bottom center (X11 path; layer-shell handles its own positioning)
        if not (_HAS_LAYER_SHELL and _IS_WAYLAND):
            self._reposition()

        # Poll at ~10fps
        GLib.timeout_add(100, self._tick)

    def _reposition(self):
        """Position the window at bottom center of screen (X11 only)."""
        display = Gdk.Display.get_default()
        if display is None:
            return
        # Get primary monitor geometry
        try:
            # GTK 3.22+
            monitor = display.get_primary_monitor()
            if monitor is None:
                monitor = display.get_monitor(0)
            geo = monitor.get_geometry()
        except AttributeError:
            # Older GTK
            screen = Gdk.Screen.get_default()
            n = screen.get_primary_monitor()
            geo = screen.get_monitor_geometry(n)

        x = geo.x + (geo.width - self._current_w) // 2
        y = geo.y + geo.height - MARGIN_BOTTOM - PILL_H
        self.move(x, y)
        self.resize(self._current_w, PILL_H)

    def _get_display(self):
        spin = SPIN[self._tick_count % len(SPIN)]

        if self._status == "recording":
            elapsed = int(time.monotonic() - self._rec_start)
            mm, ss = divmod(elapsed, 60)
            pulse = 0.5 + 0.5 * math.sin(self._tick_count * 0.5)
            col = (COL_RED[0], COL_RED[1], COL_RED[2], 0.5 + 0.5 * pulse)
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
            return ("\u2699", "Check permissions", COL_GOLD)

        else:
            return ("\u25CC", "Samvad", COL_TEAL)

    def _read_state(self):
        try:
            if not STATE_FILE.exists():
                return
            raw = STATE_FILE.read_text()
            if not raw.strip():
                return
            data = json.loads(raw)
            new_status = data.get("status", "idle")

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

    def _tick(self):
        self._tick_count += 1
        self._read_state()

        if self._status == "done" and time.monotonic() - self._done_time > 3:
            self._status = "idle"
        if self._status == "error" and time.monotonic() - self._err_time > 4:
            self._status = "idle"

        # Resize pill based on text
        _, label, _ = self._get_display()
        text_w = len(label) * 8 + 48
        new_w = max(PILL_W, min(300, int(text_w)))
        if abs(self._current_w - new_w) > 2:
            self._current_w = new_w
            if not (_HAS_LAYER_SHELL and _IS_WAYLAND):
                self._reposition()
            else:
                self.resize(self._current_w, PILL_H)

        if self._status in VISIBLE_STATES:
            if not self._visible:
                self._visible = True
                self.show_all()
        else:
            if self._visible:
                self._visible = False
                self.hide()

        self.queue_draw()
        return True  # keep timer alive

    def _on_draw(self, widget, cr):
        # Clear
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        w = self.get_allocated_width()
        h = self.get_allocated_height()

        # Background
        bg = {
            "recording":    COL_BG_REC,
            "transcribing": COL_BG_WORK,
            "translating":  COL_BG_WORK,
            "polishing":    COL_BG_WORK,
            "done":         COL_BG_DONE,
            "error":        COL_BG_ERR,
            "perm":         COL_BG_PERM,
        }.get(self._status, COL_BG)

        _rounded_rect(cr, 0, 0, w, h, PILL_RADIUS)
        cr.set_source_rgba(*bg)
        cr.fill_preserve()

        # Border
        border_col = {
            "recording":    COL_RED,
            "transcribing": COL_TEAL,
            "translating":  COL_TEAL,
            "polishing":    COL_TEAL,
            "done":         COL_GREEN,
            "error":        COL_RED,
            "perm":         COL_GOLD,
        }.get(self._status, COL_DIM)
        cr.set_source_rgba(border_col[0], border_col[1], border_col[2], 0.5)
        cr.set_line_width(1.0)
        cr.stroke()

        # Icon + label
        icon, label, icon_col = self._get_display()

        cr.set_source_rgba(*icon_col)
        cr.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        cr.set_font_size(14)
        cr.move_to(12, h - 10)
        cr.show_text(icon)

        cr.set_source_rgba(*COL_WHITE)
        cr.set_font_size(12)
        cr.move_to(32, h - 11)
        cr.show_text(label)

        return False


def main():
    try:
        STATE_FILE.write_text(json.dumps({"status": "idle"}))
    except Exception:
        pass

    win = OverlayWindow()
    win.connect("destroy", Gtk.main_quit)
    # Start hidden
    Gtk.main()


if __name__ == "__main__":
    main()
