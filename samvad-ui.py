#!/usr/bin/env python3
"""
samvad-ui.py — Enhanced Textual terminal interface for Samvad

Enhancements over v1:
  • textual-plotext live waveform during recording (falls back to block chars)
  • Digits widget for large real-time recording timer
  • Animated sine-wave on idle screen
  • Bordered panels (round borders, teal/green/red accents)
  • Indeterminate ProgressBar during transcription
  • Richer history & settings views

Run:
  uv run --with "textual>=0.70" --with "textual-plotext" python samvad-ui.py
"""
from __future__ import annotations
import asyncio, json, math, platform, time
from pathlib import Path

_OS = platform.system()   # "Darwin" | "Windows"

from rich.markup import escape
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, Center
from textual.reactive import reactive
from textual.widgets import Static, ContentSwitcher, Digits, ProgressBar

try:
    from textual_plotext import PlotextPlot
    HAS_PLOTEXT = True
except ImportError:
    HAS_PLOTEXT = False

# ── Palette ────────────────────────────────────────────────────────────────────
TEAL  = "#3fb8a9"
MUTED = "#666666"
DIM   = "#333333"
RED   = "#e05555"
GREEN = "#4ec94e"
GOLD  = "#d4a520"
BG    = "#0a0a0a"
BG2   = "#111111"
BG3   = "#161616"

# ── Data ───────────────────────────────────────────────────────────────────────
LANGUAGES = [
    ("en-IN", "English"),
    ("hi-IN", "Hindi"),
    ("hi-EN", "Hinglish → English"),
    ("ta-IN", "Tamil"),
    ("te-IN", "Telugu"),
    ("ml-IN", "Malayalam"),
    ("kn-IN", "Kannada"),
    ("mr-IN", "Marathi"),
    ("gu-IN", "Gujarati"),
    ("bn-IN", "Bengali"),
    ("pa-IN", "Punjabi"),
    ("od-IN", "Odia"),
]
MODES = [
    ("direct",     "Direct — transcribe as spoken"),
    ("to_english", "→ English — translate output"),
    ("polish",     "Polish — AI clean-up"),
]
SPIN   = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
VBLOCK = " ▁▂▃▄▅▆▇█"

_SETTINGS: list[tuple[str, str, str]] = (
    [("sep", "", "LANGUAGE")]
    + [("lang", c, l) for c, l in LANGUAGES]
    + [("sep", "", "MODE")]
    + [("mode", c, l) for c, l in MODES]
)
_SEL_IDX = [i for i, (t, *_) in enumerate(_SETTINGS) if t != "sep"]

# ── Waveform widget (PlotextPlot or block-char fallback) ───────────────────────
if HAS_PLOTEXT:
    class WaveformWidget(PlotextPlot):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self._amps: list[float] = []

        def set_amps(self, amps: list[float]) -> None:
            self._amps = amps[-80:]
            self.refresh()

        def compose_plotext(self) -> None:
            plt = self.plt
            plt.clear_figure()
            plt.canvas_color("black")
            plt.axes_color("black")
            plt.ticks_color("bright-green")
            y = self._amps[-60:] if self._amps else [0.0, 0.0]
            x = list(range(len(y)))
            plt.bar(x, y, color="bright-green", width=1.0)
            plt.ylim(0, 1.0)
            plt.xlim(0, 60)
            plt.xticks([])
            plt.yticks([])
else:
    class WaveformWidget(Static):  # type: ignore[no-redef]
        def __init__(self, **kwargs) -> None:
            super().__init__("", **kwargs)
            self._amps: list[float] = []

        def set_amps(self, amps: list[float]) -> None:
            self._amps = amps
            self._redraw()

        def _redraw(self) -> None:
            w = 70
            recent = (
                self._amps[-w:]
                if len(self._amps) >= w
                else [0.0] * (w - len(self._amps)) + self._amps
            )
            parts: list[str] = []
            for a in recent:
                color = RED if a > 0.75 else GOLD if a > 0.45 else TEAL
                bar = VBLOCK[min(int(a * 8), 8)]
                parts.append(f"[{color}]{bar}[/]")
            self.update("".join(parts))

# ── CSS ────────────────────────────────────────────────────────────────────────
CSS = f"""
Screen {{ background: {BG}; }}

/* ── Header ── */
#hdr {{
    height: 1;
    background: {BG2};
    layout: horizontal;
    padding: 0 2;
}}
#hdr-title  {{ color: {TEAL}; text-style: bold; width: auto; }}
#hdr-vsep   {{ color: {DIM}; width: 3; content-align: center middle; }}
#hdr-sub    {{ color: {DIM}; width: auto; }}
#hdr-status {{ color: {MUTED}; width: 1fr; content-align: right middle; }}

/* ── Switcher fills remaining height ── */
ContentSwitcher {{ height: 1fr; }}
ContentSwitcher > * {{ height: 1fr; }}

/* ── Footer ── */
#footer {{ height: 1; background: {BG2}; color: {DIM}; padding: 0 2; }}

/* ═══════════════ IDLE ═══════════════ */
#idle-view {{
    align: center middle;
    layout: vertical;
    padding: 1 4;
}}
#idle-title {{
    color: {TEAL};
    text-style: bold;
    text-align: center;
    width: 100%;
}}
#idle-wave {{
    text-align: center;
    width: 100%;
    margin-top: 1;
}}
#idle-panel {{
    border: round {TEAL};
    padding: 0 2;
    margin-top: 2;
    width: 100%;
    height: auto;
}}
#idle-instr {{
    color: {MUTED};
    text-align: center;
    width: 100%;
    margin-top: 2;
}}

/* ═══════════════ RECORDING ═══════════════ */
#rec-view {{
    layout: vertical;
    padding: 0 2;
}}
#rec-title-row {{
    height: auto;
    layout: horizontal;
    align: center middle;
    padding: 1 0 0 0;
    width: 100%;
}}
#rec-icon {{
    color: {RED};
    text-style: bold;
    width: auto;
}}
#rec-label {{
    color: {RED};
    text-style: bold;
    width: auto;
    margin-left: 1;
}}
#rec-digits {{
    color: {RED};
    width: auto;
    margin-left: 3;
}}
#rec-spin {{
    color: {RED};
    width: auto;
    margin-left: 2;
    content-align: left bottom;
}}
WaveformWidget {{
    height: 1fr;
    margin: 1 0;
    border: round {DIM};
}}
#rec-instr {{
    height: auto;
    text-align: center;
    color: {DIM};
    padding-bottom: 1;
}}

/* ═══════════════ WORKING ═══════════════ */
#work-view {{
    align: center middle;
    layout: vertical;
    padding: 2 4;
}}
#work-title {{
    color: {TEAL};
    text-style: bold;
    text-align: center;
    width: 100%;
}}
#work-pbar {{
    width: 60;
    margin-top: 2;
}}
#work-sub {{
    color: {MUTED};
    text-align: center;
    width: 100%;
    margin-top: 2;
}}
#work-steps {{
    color: {DIM};
    text-align: center;
    width: 100%;
    margin-top: 1;
}}

/* ═══════════════ DONE ═══════════════ */
#done-view {{
    align: center middle;
    layout: vertical;
    padding: 2 4;
}}
#done-panel {{
    border: round {GREEN};
    padding: 1 3;
    width: 100%;
    height: auto;
}}
#done-title {{
    color: {GREEN};
    text-style: bold;
    text-align: center;
    width: 100%;
}}
#done-sep {{
    color: {DIM};
    text-align: center;
    width: 100%;
    margin-top: 1;
}}
#done-text {{
    color: #ffffff;
    text-align: center;
    width: 100%;
    margin-top: 1;
}}
#done-meta {{
    color: {MUTED};
    text-align: center;
    width: 100%;
    margin-top: 1;
}}
#done-hint {{
    color: {DIM};
    text-align: center;
    width: 100%;
    margin-top: 2;
}}

/* ═══════════════ ERROR ═══════════════ */
#err-view {{
    align: center middle;
    layout: vertical;
    padding: 2 4;
}}
#err-panel {{
    border: round {RED};
    padding: 1 3;
    width: 70;
    max-width: 95%;
    height: auto;
}}
#err-title {{
    color: {RED};
    text-style: bold;
    text-align: center;
    width: 100%;
}}
#err-msg {{
    color: {RED};
    text-align: center;
    width: 100%;
    margin-top: 1;
}}
#err-hint {{
    color: {MUTED};
    text-align: center;
    width: 100%;
    margin-top: 2;
}}

/* ═══════════════ PERMISSIONS ═══════════════ */
#perm-view {{
    align: center middle;
    layout: vertical;
    padding: 2 4;
}}
#perm-panel {{
    border: round {GOLD};
    padding: 1 3;
    width: 60;
    max-width: 95%;
    height: auto;
}}
#perm-title {{
    color: {GOLD};
    text-style: bold;
    text-align: center;
    width: 100%;
}}
#perm-sep {{
    color: {DIM};
    text-align: center;
    width: 100%;
    margin-top: 1;
}}
#perm-im {{
    text-align: left;
    width: 100%;
    margin-top: 1;
}}
#perm-ax {{
    text-align: left;
    width: 100%;
    margin-top: 1;
}}
#perm-instr {{
    color: {MUTED};
    text-align: center;
    width: 100%;
    margin-top: 2;
}}

/* ═══════════════ SETTINGS ═══════════════ */
#settings-view {{
    padding: 1 3;
    overflow-y: auto;
}}
#settings-header {{
    color: {TEAL};
    text-style: bold;
    margin-bottom: 1;
}}

/* ═══════════════ HISTORY ═══════════════ */
#history-view {{
    padding: 1 3;
    overflow-y: auto;
}}
#history-header {{
    color: {TEAL};
    text-style: bold;
    margin-bottom: 1;
}}
"""


class SamvadApp(App[None]):
    CSS = CSS

    BINDINGS = [
        Binding("ctrl+c",  "quit_app",         show=False),
        Binding("s",       "open_settings",    show=False),
        Binding("h",       "open_history",     show=False),
        Binding("l",       "cycle_lang",       show=False),
        Binding("m",       "cycle_mode",       show=False),
        Binding("escape",  "back",             show=False),
        Binding("up",      "settings_up",      show=False),
        Binding("down",    "settings_down",    show=False),
        Binding("enter",   "settings_select",  show=False),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._status   = "init"
        self._view     = "idle"
        self._lang     = "en-IN"
        self._mode     = "direct"
        self._has_key  = False
        self._last_text = ""
        self._err_msg  = ""
        self._history: list[dict] = []
        self._amps:    list[float] = []
        self._rec_start = 0.0
        self._done_time = 0.0      # when last paste completed
        self._spin_idx  = 0
        self._t         = 0.0      # time counter for animations
        self._sel_pos   = 0
        self._perm      = {"im": False, "ax": False}
        self._perm_sel  = 0   # 0 = Input Monitoring, 1 = Accessibility
        self._ptt_key   = "fn" if _OS == "Darwin" else "Right Ctrl"
        self._core_stdin = None

    # ── Helpers ────────────────────────────────────────────────────────────────
    def _lang_label(self, code: str = "") -> str:
        code = code or self._lang
        return next((l for c, l in LANGUAGES if c == code), code)

    def _mode_label(self, code: str = "") -> str:
        code = code or self._mode
        return next((l for c, l in MODES if c == code), code)

    def _update_ptt_instructions(self) -> None:
        """Refresh every instruction label with the correct PTT key name."""
        k = self._ptt_key
        try:
            self.query_one("#idle-instr", Static).update(
                f"Hold [{TEAL}]\\[{k}][/] anywhere to speak  ·  release to paste"
            )
            self.query_one("#rec-instr", Static).update(
                f"Release [{TEAL}]\\[{k}][/] to transcribe and paste"
            )
            self.query_one("#done-hint", Static).update(
                f"[{DIM}]Hold \\[{k}] to record again  ·  \\[Esc] to dismiss[/]"
            )
            self.query_one("#err-hint", Static).update(
                f"[{MUTED}]Hold \\[{k}] to try again[/]"
            )
        except Exception:
            pass

    def _send(self, msg: dict) -> None:
        if self._core_stdin:
            try:
                self._core_stdin.write((json.dumps(msg) + "\n").encode())
            except Exception:
                pass

    def _sine_wave(self, width: int = 60) -> str:
        """Animated sine wave for idle screen using dot/circle chars."""
        CHARS = " ·∘◦○◦∘·"
        out: list[str] = []
        for i in range(width):
            phase = (i / width) * 4 * math.pi + self._t * 1.2
            y = (math.sin(phase) + 1) / 2
            ch = CHARS[int(y * (len(CHARS) - 1))]
            out.append(ch)
        return f"[{DIM}]{''.join(out)}[/]"

    # ── Compose ────────────────────────────────────────────────────────────────
    def compose(self) -> ComposeResult:
        # Header
        with Container(id="hdr"):
            yield Static("SAMVAD", id="hdr-title")
            yield Static(" ·", id="hdr-vsep")
            yield Static("voice to text", id="hdr-sub")
            yield Static("initializing…", id="hdr-status")

        with ContentSwitcher(id="switcher", initial="idle-view"):

            # ── Idle ──────────────────────────────────────────────────────
            with Container(id="idle-view"):
                yield Static("◌  SAMVAD", id="idle-title")
                yield Static("", id="idle-wave")
                with Container(id="idle-panel"):
                    yield Static("", id="idle-info")
                yield Static(
                    f"Hold [{TEAL}]\\[{self._ptt_key}][/] anywhere to speak  ·  release to paste",
                    id="idle-instr",
                )

            # ── Recording ─────────────────────────────────────────────────
            with Container(id="rec-view"):
                with Horizontal(id="rec-title-row"):
                    yield Static("⏺", id="rec-icon")
                    yield Static("RECORDING", id="rec-label")
                    yield Digits("00:00", id="rec-digits")
                    yield Static("⠋", id="rec-spin")
                yield WaveformWidget(id="waveform")
                yield Static(
                    f"Release [{TEAL}]\\[{self._ptt_key}][/] to transcribe and paste",
                    id="rec-instr",
                )

            # ── Working ───────────────────────────────────────────────────
            with Container(id="work-view"):
                yield Static("⠋  Processing…", id="work-title")
                yield ProgressBar(total=None, id="work-pbar", show_eta=False)
                yield Static("", id="work-sub")
                yield Static("", id="work-steps")

            # ── Done ──────────────────────────────────────────────────────
            with Container(id="done-view"):
                with Container(id="done-panel"):
                    yield Static("✓  Pasted at cursor", id="done-title")
                    yield Static(f"[{DIM}]{'─' * 50}[/]", id="done-sep")
                    yield Static("", id="done-text")
                    yield Static("", id="done-meta")
                yield Static(
                    f"[{DIM}]Hold \\[{self._ptt_key}] to record again  ·  \\[Esc] to dismiss[/]",
                    id="done-hint",
                )

            # ── Error ─────────────────────────────────────────────────────
            with Container(id="err-view"):
                with Container(id="err-panel"):
                    yield Static("✗  Error", id="err-title")
                    yield Static("", id="err-msg")
                yield Static(
                    f"[{MUTED}]Hold \\[{self._ptt_key}] to try again[/]",
                    id="err-hint",
                )

            # ── Permissions ───────────────────────────────────────────────
            with Container(id="perm-view"):
                with Container(id="perm-panel"):
                    yield Static("⚙  Permission Setup", id="perm-title")
                    yield Static(f"[{DIM}]{'─' * 36}[/]", id="perm-sep")
                    yield Static("", id="perm-im")
                    yield Static("", id="perm-ax")
                    yield Static(
                        f"\n  [{DIM}]↑↓ select  ·  Enter = open grant dialog[/]",
                        id="perm-keys",
                    )
                yield Static("", id="perm-instr")

            # ── Settings ──────────────────────────────────────────────────
            with Container(id="settings-view"):
                yield Static("[bold]Settings[/]", id="settings-header")
                yield Static("", id="settings-list")

            # ── History ───────────────────────────────────────────────────
            with Container(id="history-view"):
                yield Static("[bold]History[/]", id="history-header")
                yield Static("", id="history-list")

        yield Static(
            "\\[S] Settings  \\[H] History  \\[L] Language  \\[M] Mode  \\[Ctrl+C] Quit",
            id="footer",
        )

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    async def on_mount(self) -> None:
        self.set_interval(0.1, self._tick)
        self.run_worker(self._run_core())

    # ── Animation tick ────────────────────────────────────────────────────────
    def _tick(self) -> None:
        self._t += 0.1
        self._spin_idx = (self._spin_idx + 1) % len(SPIN)
        spin = SPIN[self._spin_idx]

        # ── Idle animations ──
        if self._status == "idle" and self._view == "idle":
            PULSES = [
                f"[bold {TEAL}]◌  SAMVAD  ◌[/]",
                f"[bold {TEAL}]◎  SAMVAD  ◎[/]",
                f"[bold {TEAL}]◉  SAMVAD  ◉[/]",
                f"[bold {TEAL}]◎  SAMVAD  ◎[/]",
            ]
            frame = int(self._t * 1.5) % len(PULSES)
            try:
                self.query_one("#idle-title", Static).update(PULSES[frame])
                self.query_one("#idle-wave",  Static).update(self._sine_wave())
            except Exception:
                pass

        # ── Recording animations ──
        elif self._status == "recording":
            elapsed = int(time.monotonic() - self._rec_start)
            mm, ss = divmod(elapsed, 60)
            try:
                self.query_one("#rec-digits", Digits).update(f"{mm:02d}:{ss:02d}")
                self.query_one("#rec-spin",   Static).update(
                    f"[{RED}]{spin}[/]"
                )
            except Exception:
                pass

        # ── Working animations ──
        elif self._status in ("transcribing", "translating", "polishing"):
            STEP_ICONS = {
                "transcribing": f"[{TEAL}]⠿[/] Transcribing  [{DIM}]→[/]  [{DIM}]Translate  →  Polish[/]",
                "translating":  f"[{DIM}]✓ Transcribed  [{DIM}]→[/]  [{TEAL}]⠿[/] Translating  [{DIM}]→  Polish[/]",
                "polishing":    f"[{DIM}]✓ Transcribed  →  ✓ Translated  [{DIM}]→[/]  [{TEAL}]⠿[/] Polishing[/]",
            }
            lbl_map = {
                "transcribing": "Transcribing with saaras:v3",
                "translating":  "Translating to English",
                "polishing":    "AI Polish",
            }
            lbl = lbl_map.get(self._status, "Processing")
            try:
                self.query_one("#work-title", Static).update(
                    f"[bold {TEAL}]{spin}  {lbl}…[/]"
                )
                self.query_one("#work-steps", Static).update(
                    STEP_ICONS.get(self._status, "")
                )
            except Exception:
                pass

        # ── Done animations ──
        elif self._status == "done":
            age     = time.monotonic() - self._done_time
            remain  = max(0, 10 - int(age))
            # Pulsing checkmark: ✓ ↔ ✔
            check = "✔" if int(self._t * 4) % 2 == 0 else "✓"
            # Animated separator: dots chase across the line
            SEP_W  = 52
            pos    = int((age % 2.0) / 2.0 * SEP_W)
            sep    = (
                f"[{DIM}]{'─' * pos}[/]"
                f"[{GREEN}]◆[/]"
                f"[{DIM}]{'─' * (SEP_W - pos)}[/]"
            )
            # Countdown hint
            if remain > 0:
                hint = (
                    f"[{DIM}]Hold \\[fn] again  ·  \\[Esc] dismiss  ·  "
                    f"clears in [{TEAL}]{remain}s[/][/]"
                )
            else:
                # Auto-dismiss
                self._status = "idle"
                self._refresh_ui()
                return
            try:
                self.query_one("#done-title", Static).update(
                    f"[bold {GREEN}]{check}  Pasted at cursor[/]"
                )
                self.query_one("#done-sep",   Static).update(sep)
                self.query_one("#done-hint",  Static).update(hint)
            except Exception:
                pass

    # ── Show panel / refresh UI ───────────────────────────────────────────────
    def _switch(self, view_id: str) -> None:
        try:
            self.query_one("#switcher", ContentSwitcher).current = view_id
        except Exception:
            pass

    def _refresh_ui(self) -> None:
        status, view = self._status, self._view

        # Header status
        LABELS = {
            "init": "initializing…", "perm": "waiting for permissions…",
            "idle": "ready", "recording": "recording…",
            "transcribing": "transcribing…", "translating": "translating…",
            "polishing": "polishing…", "done": "done!", "error": "error",
        }
        try:
            self.query_one("#hdr-status", Static).update(
                f"[{MUTED}]{LABELS.get(status, status)}[/]"
            )
        except Exception:
            pass

        # Footer
        try:
            if status == "perm":
                txt = f"[{DIM}]↑↓ Select permission   Enter Grant   Ctrl+C Quit[/]"
            elif view == "settings":
                txt = f"[{DIM}]↑↓ Navigate   Enter Select   Esc Close[/]"
            elif view == "history":
                txt = f"[{DIM}]\\[Esc] or \\[H] Close[/]"
            else:
                txt = "\\[S] Settings  \\[H] History  \\[L] Language  \\[M] Mode  \\[Ctrl+C] Quit"
            self.query_one("#footer", Static).update(txt)
        except Exception:
            pass

        # Show correct panel
        if view == "settings":
            self._refresh_settings()
            self._switch("settings-view")
        elif view == "history":
            self._refresh_history()
            self._switch("history-view")
        elif status == "perm":
            self._refresh_perm()
            self._switch("perm-view")
        elif status == "recording":
            self._switch("rec-view")
        elif status in ("transcribing", "translating", "polishing"):
            lbl_map = {
                "transcribing": "Transcribing with saaras:v3",
                "translating":  "Translating to English",
                "polishing":    "AI Polish",
            }
            try:
                self.query_one("#work-sub", Static).update(
                    f"[{MUTED}]{lbl_map.get(status, 'Processing…')}[/]"
                )
                self.query_one("#work-title", Static).update(
                    f"[bold {TEAL}]{SPIN[self._spin_idx]}  {lbl_map.get(status, 'Processing')}…[/]"
                )
            except Exception:
                pass
            self._switch("work-view")
        elif status == "done":
            txt = escape(self._last_text[:250])
            try:
                self.query_one("#done-text", Static).update(f"[#dddddd]{txt}[/]")
                mode_short = {
                    "direct": "Direct", "to_english": "→ English", "polish": "Polish",
                }.get(self._mode, self._mode_label())
                self.query_one("#done-meta", Static).update(
                    f"[{MUTED}]{escape(self._lang_label())}  ·  {escape(mode_short)}[/]"
                )
            except Exception:
                pass
            self._switch("done-view")
        elif status == "error":
            try:
                self.query_one("#err-msg", Static).update(
                    f"[{RED}]{escape(self._err_msg)}[/]"
                )
            except Exception:
                pass
            self._switch("err-view")
        else:
            self._refresh_idle()
            self._switch("idle-view")

    def _refresh_idle(self) -> None:
        api_ok    = self._has_key
        api_color = TEAL if api_ok else RED
        api_text  = "● saaras:v3  connected" if api_ok else "✗ no API key"
        # Short mode labels so the box never needs to wrap
        mode_short = {
            "direct":     "Direct",
            "to_english": "→ English",
            "polish":     "Polish",
        }.get(self._mode, self._mode_label())
        lines = [
            f"  [{MUTED}]Language[/]  [{TEAL}]{escape(self._lang_label())}[/]",
            f"  [{MUTED}]Mode[/]      [{TEAL}]{escape(mode_short)}[/]",
            f"  [{api_color}]{api_text}[/]",
        ]
        if self._history:
            h = self._history[-1]
            prev = escape(h["text"][:52] + ("…" if len(h["text"]) > 52 else ""))
            lines += [
                f"  [{DIM}]{'─' * 38}[/]",
                f"  [{MUTED}]Last  [{TEAL}]{escape(h['time'])}[/]  [{DIM}]{escape(h['lang'])}[/]",
                f"  [#888888]{prev}[/]",
            ]
        try:
            self.query_one("#idle-info", Static).update("\n".join(lines))
        except Exception:
            pass

    def _refresh_perm(self) -> None:
        im, ax = self._perm["im"], self._perm["ax"]
        perms = [
            ("perm-im", im, "Input Monitoring"),
            ("perm-ax", ax, "Accessibility"),
        ]
        for i, (wid, granted, label) in enumerate(perms):
            is_sel = (i == self._perm_sel)
            if granted:
                line = f"  [{GREEN}]  [✓] {label}[/]"
            elif is_sel:
                line = f"  [bold {TEAL}]▶ [ ] {label}[/]  [{DIM}]← press Enter[/]"
            else:
                line = f"  [{MUTED}]  [ ] {label}[/]"
            try:
                self.query_one(f"#{wid}", Static).update(line)
            except Exception:
                pass

        # Update bottom instruction
        all_granted = im and ax
        try:
            if all_granted:
                self.query_one("#perm-instr", Static).update(
                    f"[{GREEN}]  ✓ All permissions granted — starting…[/]"
                )
            else:
                self.query_one("#perm-instr", Static).update(
                    f"[{DIM}]  Checking automatically…[/]"
                )
        except Exception:
            pass

    def _refresh_settings(self) -> None:
        lines: list[str] = []
        for i, (typ, code, label) in enumerate(_SETTINGS):
            if typ == "sep":
                if lines:
                    lines.append("")
                lines.append(f"  [bold #aaaaaa]{label}[/]")
                lines.append(f"  [{DIM}]{'─' * 46}[/]")
                continue
            sel_pos_of_i = _SEL_IDX.index(i) if i in _SEL_IDX else -1
            is_sel    = (sel_pos_of_i == self._sel_pos)
            is_active = (
                (typ == "lang" and code == self._lang) or
                (typ == "mode" and code == self._mode)
            )
            dot   = f"  [{GREEN}]●[/]" if is_active else ""
            elbl  = escape(label)
            if is_sel:
                lines.append(
                    f"  [bold {TEAL}]▶  [/][bold #ffffff]{elbl}[/]{dot}"
                )
            else:
                color = GREEN if is_active else MUTED
                lines.append(f"     [{color}]{elbl}[/]{dot}")
        lines += [
            "",
            f"  [{DIM}]↑↓ Navigate   Enter Select   Esc Close[/]",
        ]
        try:
            self.query_one("#settings-list", Static).update("\n".join(lines))
        except Exception:
            pass

    def _refresh_history(self) -> None:
        if not self._history:
            txt = f"[{MUTED}]No history yet.[/]"
        else:
            lines: list[str] = []
            for i, h in enumerate(reversed(self._history)):
                prev = escape(h["text"][:80] + ("…" if len(h["text"]) > 80 else ""))
                lines.append(
                    f"[bold {TEAL}]{i + 1}.[/]  "
                    f"[{MUTED}]{escape(h['time'])}[/]  "
                    f"[{DIM}][{escape(h['lang'])}][/]"
                )
                lines.append(f"   [#cccccc]{prev}[/]")
                if i < len(self._history) - 1:
                    lines.append(f"   [{DIM}]{'─' * 60}[/]")
            txt = "\n".join(lines)
        try:
            self.query_one("#history-list", Static).update(txt)
        except Exception:
            pass

    # ── Actions ───────────────────────────────────────────────────────────────
    def action_quit_app(self) -> None:
        self._send({"cmd": "quit"})
        self.exit()

    def action_open_settings(self) -> None:
        if self._view != "settings":
            self._view = "settings"
            self._refresh_ui()

    def action_open_history(self) -> None:
        self._view = "idle" if self._view == "history" else "history"
        self._refresh_ui()

    def action_cycle_lang(self) -> None:
        if self._view in ("settings", "history"):
            return
        codes = [c for c, _ in LANGUAGES]
        self._lang = codes[(codes.index(self._lang) + 1) % len(codes)]
        self._send({"cmd": "set_lang", "lang": self._lang})
        self._refresh_idle()

    def action_cycle_mode(self) -> None:
        if self._view in ("settings", "history"):
            return
        codes = [c for c, _ in MODES]
        self._mode = codes[(codes.index(self._mode) + 1) % len(codes)]
        self._send({"cmd": "set_mode", "mode": self._mode})
        self._refresh_idle()

    def action_back(self) -> None:
        if self._view in ("settings", "history"):
            self._view = "idle"
            self._refresh_ui()
        elif self._status == "done":
            self._status = "idle"
            self._refresh_ui()

    def _request_perm(self) -> None:
        """Press Enter on a permission row → trigger its system dialog."""
        perm_keys = ["im", "ax"]
        key = perm_keys[self._perm_sel]
        if self._perm.get(key):
            return  # already granted, skip
        self._send({"cmd": "request_perm", "perm": key})

    def action_settings_up(self) -> None:
        if self._status == "perm":
            self._perm_sel = max(0, self._perm_sel - 1)
            self._refresh_perm()
            return
        if self._view != "settings":
            return
        self._sel_pos = max(0, self._sel_pos - 1)
        self._refresh_settings()

    def action_settings_down(self) -> None:
        if self._status == "perm":
            self._perm_sel = min(1, self._perm_sel + 1)
            self._refresh_perm()
            return
        if self._view != "settings":
            return
        self._sel_pos = min(len(_SEL_IDX) - 1, self._sel_pos + 1)
        self._refresh_settings()

    def action_settings_select(self) -> None:
        if self._status == "perm":
            self._request_perm()
            return
        if self._view != "settings":
            return
        typ, code, _ = _SETTINGS[_SEL_IDX[self._sel_pos]]
        if typ == "lang":
            self._lang = code
            if self._lang == "hi-EN" and self._mode == "direct":
                self._mode = "to_english"
            self._send({"cmd": "set_lang", "lang": self._lang})
        elif typ == "mode":
            self._mode = code
            self._send({"cmd": "set_mode", "mode": self._mode})
        self._refresh_settings()

    # ── Core subprocess ───────────────────────────────────────────────────────
    async def _run_core(self) -> None:
        dir_ = Path(__file__).parent
        args = [
            "uv", "run", "--python", "3.11", "--no-project",
            "--with", "sounddevice>=0.4",
            "--with", "numpy>=1.26",
            "--with", "requests>=2.28",
        ]
        if _OS == "Darwin":
            args += [
                "--with", "pyobjc-framework-Cocoa>=10",
                "--with", "pyobjc-framework-Quartz>=10",
            ]
        elif _OS == "Windows":
            args += [
                "--with", "pynput>=1.7",
                "--with", "pyperclip>=1.8",
            ]
        args += ["python", str(dir_ / "samvad-core.py")]
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=None,
        )
        self._core_stdin = proc.stdin
        try:
            async for raw in proc.stdout:
                line = raw.decode(errors="replace").strip()
                if not line:
                    continue
                try:
                    self._handle_core_msg(json.loads(line))
                except Exception:
                    pass
        finally:
            self.exit()

    def _handle_core_msg(self, msg: dict) -> None:
        t = msg.get("type", "")

        if t == "init":
            self._has_key = bool(msg.get("has_key"))

        elif t == "perm":
            self._perm   = {"im": bool(msg.get("im")), "ax": bool(msg.get("ax"))}
            self._status = "perm"
            # Auto-advance selector to first ungranged permission
            if self._perm["im"] and not self._perm["ax"]:
                self._perm_sel = 1
            elif not self._perm["im"]:
                self._perm_sel = 0
            self._refresh_perm()
            self._switch("perm-view")
            return

        elif t == "ready":
            self._status  = "idle"
            self._lang    = msg.get("lang", self._lang)
            self._mode    = msg.get("mode", self._mode)
            self._has_key = bool(msg.get("has_key"))
            self._ptt_key = msg.get("ptt_key", self._ptt_key)
            self._update_ptt_instructions()

        elif t == "status":
            self._status = msg.get("status", self._status)
            if self._status == "recording":
                self._rec_start = time.monotonic()
                self._amps      = []
                self._view      = "idle"
                # Reset timer display
                try:
                    self.query_one("#rec-digits", Digits).update("00:00")
                except Exception:
                    pass
            elif self._status in ("transcribing", "translating", "polishing"):
                self._view = "idle"
                # Reset progress bar for each new work phase
                try:
                    self.query_one("#work-pbar", ProgressBar).update(total=None)
                except Exception:
                    pass

        elif t == "done":
            self._status    = "done"
            self._done_time = time.monotonic()
            self._last_text = msg.get("text", "")
            self._view      = "idle"
            self._history.append({
                "text": self._last_text,
                "time": msg.get("time", ""),
                "lang": msg.get("lang", ""),
            })

        elif t == "error":
            self._status  = "error"
            self._err_msg = msg.get("msg", "unknown error")
            self._view    = "idle"

        elif t == "amp":
            amp = float(msg.get("value", 0))
            self._amps.append(amp)
            if len(self._amps) > 80:
                self._amps.pop(0)
            # Push to waveform widget without full UI refresh
            if self._status == "recording":
                try:
                    self.query_one("#waveform", WaveformWidget).set_amps(self._amps)
                except Exception:
                    pass
            return  # no full refresh for amp

        self._refresh_ui()


if __name__ == "__main__":
    SamvadApp().run()
