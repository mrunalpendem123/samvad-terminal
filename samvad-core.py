#!/usr/bin/env python3
"""
samvad-core — cross-platform backend (macOS + Windows + Linux)
PTT key: fn (macOS) | Right Ctrl (Windows/Linux)
Communicates with samvad-ui.py via JSON lines on stdio.
"""
from __future__ import annotations
import atexit, io, json, os, platform, re, shutil, signal, subprocess, sys
import threading, time, wave
from datetime import datetime
from pathlib import Path

import requests

PLATFORM = platform.system()   # "Darwin" | "Windows" | "Linux"

# ── Linux display server detection ────────────────────────────────────────────
_LINUX_SESSION = "x11"  # default
if PLATFORM == "Linux":
    _sess = os.environ.get("XDG_SESSION_TYPE", "").lower()
    if _sess == "wayland":
        _LINUX_SESSION = "wayland"
    elif _sess == "x11":
        _LINUX_SESSION = "x11"
    elif os.environ.get("WAYLAND_DISPLAY"):
        _LINUX_SESSION = "wayland"
    else:
        _LINUX_SESSION = "x11"

# ── Cross-platform lock files ──────────────────────────────────────────────────
if PLATFORM == "Windows":
    _TMP = Path(os.environ.get("TEMP", "C:\\Temp"))
else:
    _TMP = Path("/tmp")
_INSTANCE_LOCK = _TMP / ".samvad_instance.lock"
_PASTE_LOCK    = _TMP / ".samvad_paste.lock"

# ── Audio ──────────────────────────────────────────────────────────────────────
try:
    import sounddevice as sd
    import numpy as np
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

# ── macOS-specific ─────────────────────────────────────────────────────────────
HAS_OBJC = False
_ax = _cg = None
if PLATFORM == "Darwin":
    import ctypes
    try:
        import AppKit  # noqa: F401
        from Foundation import NSRunLoop, NSDate, NSDictionary, NSNumber
        from Quartz import (
            CGEventTapCreate, kCGSessionEventTap, kCGHeadInsertEventTap,
            kCGEventTapOptionDefault, CGEventMaskBit, kCGEventFlagsChanged,
            CGEventGetFlags, CFMachPortCreateRunLoopSource,
            CFRunLoopAddSource, CFRunLoopGetCurrent,
            kCFRunLoopDefaultMode, CGEventTapEnable,
        )
        HAS_OBJC = True
    except ImportError:
        pass

    _ax = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
    _cg = ctypes.cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    _ax.AXIsProcessTrusted.restype             = ctypes.c_bool
    _ax.AXIsProcessTrustedWithOptions.restype  = ctypes.c_bool
    _ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
    _cg.CGPreflightListenEventAccess.restype   = ctypes.c_bool
    _cg.CGRequestListenEventAccess.restype     = ctypes.c_bool

    def _has_ax():
        return bool(_ax.AXIsProcessTrusted())

    def _request_ax_prompt():
        """Trigger macOS Accessibility prompt so Terminal appears in the list."""
        try:
            subprocess.Popen([
                sys.executable, "-c",
                "import time;"
                "from ApplicationServices import AXIsProcessTrustedWithOptions;"
                "AXIsProcessTrustedWithOptions({'AXTrustedCheckOptionPrompt': True});"
                "time.sleep(30)"
            ])
        except Exception:
            pass

    def _request_im_prompt():
        """Trigger macOS Input Monitoring prompt so Terminal appears in the list."""
        try:
            subprocess.Popen([
                sys.executable, "-c",
                "import ctypes, time;"
                "cg=ctypes.cdll.LoadLibrary("
                "'/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics');"
                "cg.CGRequestListenEventAccess.restype=ctypes.c_bool;"
                "cg.CGRequestListenEventAccess();"
                "time.sleep(30)"
            ])
        except Exception:
            pass

    def _has_im():
        # CGPreflightListenEventAccess caches its result in-process on macOS 13+.
        # Spawn a tiny subprocess to get a fresh read from the TCC database.
        try:
            r = subprocess.run(
                [sys.executable, "-c",
                 "import ctypes; cg=ctypes.cdll.LoadLibrary("
                 "'/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics');"
                 "cg.CGPreflightListenEventAccess.restype=ctypes.c_bool;"
                 "print(int(cg.CGPreflightListenEventAccess()))"],
                capture_output=True, text=True, timeout=3)
            return r.stdout.strip() == "1"
        except Exception:
            return bool(_cg.CGPreflightListenEventAccess())

    FN_FLAG = 0x800000
    PTT_KEYS_MAC = {
        "fn":      0x800000,
        "control": 0x40000,
        "option":  0x80000,
        "command": 0x100000,
    }

# ── Windows / Linux-specific ───────────────────────────────────────────────────
HAS_PYNPUT = False
PTT_KEYS_WIN = {}
if PLATFORM in ("Windows", "Linux"):
    # On Wayland, pynput needs evdev backend — ensure user is in 'input' group
    if PLATFORM == "Linux" and _LINUX_SESSION == "wayland":
        os.environ.setdefault("PYNPUT_BACKEND", "xorg")  # try X first via XWayland
    try:
        from pynput import keyboard as _pynput_kb
        if PLATFORM == "Windows":
            import pyperclip
        HAS_PYNPUT = True
        PTT_KEYS_WIN = {
            "right_ctrl":  _pynput_kb.Key.ctrl_r,
            "left_ctrl":   _pynput_kb.Key.ctrl_l,
            "right_alt":   _pynput_kb.Key.alt_r,
            "left_alt":    _pynput_kb.Key.alt_l,
            "right_shift": _pynput_kb.Key.shift_r,
        }
    except ImportError:
        pass

PTT_KEY_DISPLAY = {
    "fn": "fn", "control": "Control", "option": "Option", "command": "Command",
    "right_ctrl": "Right Ctrl", "left_ctrl": "Left Ctrl",
    "right_alt": "Right Alt", "left_alt": "Left Alt",
    "right_shift": "Right Shift",
}

# ── Language/mode ──────────────────────────────────────────────────────────────
LANGUAGES = [
    ("en-IN", "en-IN", "English"),
    ("hi-IN", "hi-IN", "Hindi"),
    ("hi-EN", "hi-IN", "Hinglish -> English"),
    ("ta-IN", "ta-IN", "Tamil"),
    ("te-IN", "te-IN", "Telugu"),
    ("ml-IN", "ml-IN", "Malayalam"),
    ("kn-IN", "kn-IN", "Kannada"),
    ("mr-IN", "mr-IN", "Marathi"),
    ("gu-IN", "gu-IN", "Gujarati"),
    ("bn-IN", "bn-IN", "Bengali"),
    ("pa-IN", "pa-IN", "Punjabi"),
    ("od-IN", "od-IN", "Odia"),
]
LANG_MAP = {c: (a, n) for c, a, n in LANGUAGES}

# ── API key ────────────────────────────────────────────────────────────────────
def _load_key():
    k = os.environ.get("SARVAM_API_KEY", "")
    if k: return k
    for p in [Path(__file__).parent / ".env",
              Path.home() / ".samvad" / ".env",
              Path.home() / "Desktop" / "sarvam" / "backend" / ".env"]:
        if p.exists():
            for line in p.read_text(encoding="utf-8-sig").splitlines():
                m = re.match(r'^SARVAM_API_KEY\s*=\s*["\']?([^"\']+)["\']?', line.strip())
                if m: return m.group(1).strip()
    return ""

# ── JSON I/O ───────────────────────────────────────────────────────────────────
def emit(msg: dict):
    try:
        sys.stdout.write(json.dumps(msg) + "\n")
        sys.stdout.flush()
    except Exception:
        pass

# ── Cross-platform instance lock ───────────────────────────────────────────────
def _acquire_instance_lock() -> bool:
    """Returns True if we got the lock, False if another instance is running."""
    if _INSTANCE_LOCK.exists():
        try:
            content = _INSTANCE_LOCK.read_text().strip()
            pid = int(content)
            if pid == os.getpid():
                return True  # we already hold it
            if PLATFORM == "Windows":
                import ctypes as _ct
                SYNCHRONIZE = 0x00100000
                h = _ct.windll.kernel32.OpenProcess(SYNCHRONIZE, False, pid)
                if h:
                    _ct.windll.kernel32.CloseHandle(h)
                    return False   # still running
            else:
                os.kill(pid, 0)
                # PID exists — verify it's actually a samvad/python process
                # to handle PID recycling after crash
                try:
                    r = subprocess.run(
                        ["ps", "-p", str(pid), "-o", "comm="],
                        capture_output=True, text=True, timeout=2)
                    pname = r.stdout.strip().lower()
                    if "python" in pname or "samvad" in pname:
                        return False   # still running
                    # PID recycled to a non-Python process — stale lock
                except Exception:
                    return False       # can't verify, assume running
        except (ValueError, OSError, PermissionError):
            pass   # stale lock — process is gone
    _INSTANCE_LOCK.write_text(str(os.getpid()))
    try:
        os.chmod(str(_INSTANCE_LOCK), 0o600)
    except OSError:
        pass
    atexit.register(lambda: _INSTANCE_LOCK.unlink(missing_ok=True))
    return True

# ── Cross-platform paste lock ──────────────────────────────────────────────────
_paste_mutex = threading.Lock()   # in-process guard
_PASTE_COOLDOWN = 0.5             # seconds between pastes (reduced from 1.5)
_last_paste_time = 0.0
_MAX_PASTE_RETRIES = 3

def _do_paste(text: str) -> bool:
    """Paste text at cursor. Retries if blocked by cooldown. Returns False only on hard failure."""
    global _last_paste_time

    for attempt in range(_MAX_PASTE_RETRIES):
        if not _paste_mutex.acquire(blocking=True, timeout=2.0):
            emit({"type": "error", "msg": "Paste busy — try again"})
            return False
        try:
            now = time.time()
            wait = _PASTE_COOLDOWN - (now - _last_paste_time)
            if wait > 0:
                _paste_mutex.release()
                time.sleep(wait)
                continue  # retry after cooldown

            if PLATFORM == "Darwin":
                # Save existing clipboard
                saved_clip = None
                try:
                    r = subprocess.run(["pbpaste"], capture_output=True, timeout=2)
                    if r.returncode == 0:
                        saved_clip = r.stdout
                except Exception:
                    pass

                # Paste via pbcopy + Cmd+V
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True,
                               timeout=5)
                time.sleep(0.08)
                subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke "v" using command down'],
                    check=True, timeout=5)

                # Restore clipboard after a brief delay
                if saved_clip is not None:
                    time.sleep(0.3)
                    try:
                        subprocess.run(["pbcopy"], input=saved_clip, check=False,
                                       timeout=2)
                    except Exception:
                        pass

            elif PLATFORM == "Linux":
                # Linux: detect X11 vs Wayland and use appropriate tools
                saved_clip = None

                if _LINUX_SESSION == "wayland":
                    # Wayland: wl-copy / wl-paste / wtype (or ydotool)
                    try:
                        r = subprocess.run(["wl-paste", "--no-newline"],
                                           capture_output=True, timeout=2)
                        if r.returncode == 0:
                            saved_clip = r.stdout
                    except Exception:
                        pass

                    subprocess.run(["wl-copy", "--"],
                                   input=text.encode("utf-8"), check=True, timeout=5)
                    time.sleep(0.08)

                    # Try wtype first (simulates key events on Wayland)
                    try:
                        subprocess.run(["wtype", "-M", "ctrl", "-k", "v", "-m", "ctrl"],
                                       check=True, timeout=5)
                    except FileNotFoundError:
                        # Fallback to ydotool (needs ydotoold running)
                        try:
                            subprocess.run(["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
                                           check=True, timeout=5)
                        except FileNotFoundError:
                            # Last resort: xdotool via XWayland
                            subprocess.run(["xdotool", "key", "ctrl+v"],
                                           check=True, timeout=5)

                    if saved_clip is not None:
                        time.sleep(0.3)
                        try:
                            subprocess.run(["wl-copy", "--"],
                                           input=saved_clip, check=False, timeout=2)
                        except Exception:
                            pass
                else:
                    # X11: xclip / xdotool
                    try:
                        r = subprocess.run(["xclip", "-selection", "clipboard", "-o"],
                                           capture_output=True, timeout=2)
                        if r.returncode == 0:
                            saved_clip = r.stdout
                    except Exception:
                        pass

                    subprocess.run(["xclip", "-selection", "clipboard"],
                                   input=text.encode("utf-8"), check=True, timeout=5)
                    time.sleep(0.08)
                    subprocess.run(["xdotool", "key", "ctrl+v"], check=True, timeout=5)

                    if saved_clip is not None:
                        time.sleep(0.3)
                        try:
                            subprocess.run(["xclip", "-selection", "clipboard"],
                                           input=saved_clip, check=False, timeout=2)
                        except Exception:
                            pass

            elif PLATFORM == "Windows":
                import pyperclip
                from pynput.keyboard import Controller as _KBC, Key as _Key
                saved_clip = None
                try:
                    saved_clip = pyperclip.paste()
                except Exception:
                    pass

                pyperclip.copy(text)
                time.sleep(0.08)
                kb = _KBC()
                kb.press(_Key.ctrl)
                kb.press('v')
                kb.release('v')
                kb.release(_Key.ctrl)

                if saved_clip is not None:
                    time.sleep(0.3)
                    try:
                        pyperclip.copy(saved_clip)
                    except Exception:
                        pass

            _last_paste_time = time.time()
            time.sleep(0.3)
            _paste_mutex.release()
            return True
        except subprocess.TimeoutExpired:
            _paste_mutex.release()
            emit({"type": "error", "msg": "Paste timed out — is an app focused?"})
            return False
        except Exception as e:
            _paste_mutex.release()
            emit({"type": "error", "msg": f"Paste failed: {e}"})
            return False

    emit({"type": "error", "msg": "Paste blocked by cooldown — try again"})
    return False


# ── Core ───────────────────────────────────────────────────────────────────────
class Core:
    def __init__(self):
        self.key       = _load_key()
        self.lang      = "en-IN"
        self.mode      = "direct"
        self._quit     = threading.Event()
        self._stop     = threading.Event()
        self._frames: list = []
        self._lock     = threading.Lock()
        self._tx_lock  = threading.Lock()
        self._fn_down  = False
        self._fn_release_time = 0.0
        self._tap_ready = threading.Event()
        self._tap_ok    = False
        self._recording = False
        self.ptt_key    = "fn" if PLATFORM == "Darwin" else "right_ctrl"  # Linux & Windows use right_ctrl
        self._capture_mode = False

    def _lang_name(self):
        return LANG_MAP.get(self.lang, (self.lang, self.lang))[1]

    # ── WAV helper ──────────────────────────────────────────────────────
    def _wav(self, pcm: bytes) -> bytes:
        b = io.BytesIO()
        with wave.open(b, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2)
            wf.setframerate(16000); wf.writeframes(pcm)
        return b.getvalue()

    # ── ASR ─────────────────────────────────────────────────────────────
    def _asr(self, pcm: bytes, lang_code: str) -> str:
        MAX, OVL = 16000 * 29 * 2, 16000 * 2 // 4
        def chunk(p: bytes) -> str:
            r = requests.post(
                "https://api.sarvam.ai/speech-to-text",
                headers={"api-subscription-key": self.key},
                files={"file": ("a.wav", self._wav(p), "audio/wav")},
                data={"model": "saaras:v3", "language_code": lang_code},
                timeout=60)
            r.raise_for_status()
            return r.json().get("transcript", "").strip()
        if len(pcm) <= MAX:
            return chunk(pcm)
        parts, s = [], 0
        while s < len(pcm):
            e = min(s + MAX, len(pcm))
            t = chunk(pcm[s:e])
            if t: parts.append(t)
            if e >= len(pcm): break
            s = max(e - OVL, s + 1)
        return " ".join(parts)

    # ── Translate ────────────────────────────────────────────────────────
    def _translate(self, text: str, src_lang: str) -> str:
        try:
            r = requests.post(
                "https://api.sarvam.ai/translate",
                headers={"api-subscription-key": self.key,
                         "Content-Type": "application/json"},
                json={"input": text, "source_language_code": src_lang,
                      "target_language_code": "en-IN",
                      "speaker_gender": "Male", "mode": "formal",
                      "enable_preprocessing": False},
                timeout=30)
            if r.ok:
                out = r.json().get("translated_text", "").strip()
                if out: return out
        except Exception:
            pass
        prompt = f"Translate to English, return only translation:\n\n{text}"
        ak = os.environ.get("ANTHROPIC_API_KEY", "")
        ok = os.environ.get("OPENAI_API_KEY", "")
        try:
            if ak:
                import anthropic
                c = anthropic.Anthropic(api_key=ak)
                m = c.messages.create(model="claude-haiku-4-5-20251001", max_tokens=512,
                                      messages=[{"role": "user", "content": prompt}])
                return m.content[0].text.strip()
            elif ok:
                from openai import OpenAI
                c = OpenAI(api_key=ok)
                r2 = c.chat.completions.create(model="gpt-4o-mini",
                     messages=[{"role": "user", "content": prompt}], max_tokens=512)
                return r2.choices[0].message.content.strip()
        except Exception:
            pass
        return text

    # ── Polish ───────────────────────────────────────────────────────────
    def _polish(self, text: str) -> str:
        prompt = ("Clean up this voice transcription. Fix punctuation, "
                  "capitalisation, remove filler words. Return only:\n\n" + text)
        ak = os.environ.get("ANTHROPIC_API_KEY", "")
        ok = os.environ.get("OPENAI_API_KEY", "")
        try:
            if ak:
                import anthropic
                c = anthropic.Anthropic(api_key=ak)
                m = c.messages.create(model="claude-haiku-4-5-20251001", max_tokens=1024,
                                      messages=[{"role": "user", "content": prompt}])
                return m.content[0].text.strip()
            elif ok:
                from openai import OpenAI
                c = OpenAI(api_key=ok)
                r2 = c.chat.completions.create(model="gpt-4o-mini",
                     messages=[{"role": "user", "content": prompt}], max_tokens=1024)
                return r2.choices[0].message.content.strip()
        except Exception:
            pass
        return text

    # ── Recording ────────────────────────────────────────────────────────
    def _rec_thread(self):
        self._frames = []
        def cb(indata, *_):
            self._frames.append(indata.copy())
            amp = min(float(np.max(np.abs(indata))) * 4, 1.)
            emit({"type": "amp", "value": round(amp, 3)})
        try:
            with sd.InputStream(samplerate=16000, channels=1, dtype="float32",
                                callback=cb, blocksize=1024):
                while not self._stop.is_set():
                    time.sleep(0.01)
        except Exception as e:
            emit({"type": "error", "msg": f"Mic: {e}"})

    def _start_rec(self):
        with self._lock:
            if self._recording: return
            self._recording = True
        self._stop.clear()
        emit({"type": "status", "status": "recording"})
        threading.Thread(target=self._rec_thread, daemon=True).start()

    def _stop_rec(self):
        with self._lock:
            if not self._recording: return
            self._recording = False
        self._stop.set()
        time.sleep(0.15)
        emit({"type": "status", "status": "transcribing"})
        threading.Thread(target=self._tx_thread, daemon=True).start()

    # ── Transcription + paste ─────────────────────────────────────────────
    def _tx_thread(self):
        if not self._tx_lock.acquire(blocking=True, timeout=30):
            emit({"type": "error", "msg": "Transcription busy — try again"})
            return
        try:
            frames, self._frames = self._frames, []
            if not frames:
                emit({"type": "status", "status": "idle"}); return

            # Discard recordings < 300 ms (key bounce)
            if len(frames) * 1024 / 16000 < 0.3:
                emit({"type": "status", "status": "idle"}); return

            audio = np.concatenate(frames)
            pcm   = (audio * 32767).astype(np.int16).tobytes()

            asr_lang = LANG_MAP.get(self.lang, (self.lang, ""))[0]
            text     = self._asr(pcm, asr_lang)
            if not text:
                emit({"type": "status", "status": "idle"}); return

            needs_translate = (self.lang == "hi-EN" or self.mode == "to_english")
            if needs_translate and asr_lang != "en-IN":
                emit({"type": "status", "status": "translating"})
                text = self._translate(text, asr_lang)

            if self.mode == "polish":
                emit({"type": "status", "status": "polishing"})
                text = self._polish(text)

            if not _do_paste(text):
                # Paste failed but we still have the text — report it
                # so the user can see what was transcribed
                emit({
                    "type": "done",
                    "text": text,
                    "time": datetime.now().strftime("%H:%M"),
                    "lang": self._lang_name(),
                    "paste_failed": True,
                })
                return

            emit({
                "type": "done",
                "text": text,
                "time": datetime.now().strftime("%H:%M"),
                "lang": self._lang_name(),
            })

        except Exception as e:
            emit({"type": "error", "msg": str(e)})
        finally:
            self._tx_lock.release()

    # ── macOS: CGEventTap (fn key) ────────────────────────────────────────
    def _tap_thread_macos(self):
        def _get_ptt_flag():
            return PTT_KEYS_MAC.get(self.ptt_key, FN_FLAG)

        def cb(proxy, etype, event, refcon):
            try:
                if etype == kCGEventFlagsChanged:
                    flags = CGEventGetFlags(event)

                    # ── Capture mode: detect which modifier was pressed ──
                    if self._capture_mode:
                        for name, flag in PTT_KEYS_MAC.items():
                            if flags & flag:
                                self._capture_mode = False
                                self.ptt_key = name
                                emit({"type": "ptt_key_captured", "key": name,
                                      "display": PTT_KEY_DISPLAY.get(name, name)})
                                return event
                        return event

                    ptt_flag = _get_ptt_flag()
                    fn  = bool(flags & ptt_flag)
                    now = time.time()
                    if fn and not self._fn_down:
                        if now - self._fn_release_time < 0.15:
                            return event
                        self._fn_down = True
                        threading.Thread(target=self._start_rec, daemon=True).start()
                    elif not fn and self._fn_down:
                        self._fn_down         = False
                        self._fn_release_time = now
                        threading.Thread(target=self._stop_rec, daemon=True).start()
            except Exception:
                pass
            return event

        self._tap_cb = cb
        tap = CGEventTapCreate(
            kCGSessionEventTap, kCGHeadInsertEventTap,
            kCGEventTapOptionDefault,
            CGEventMaskBit(kCGEventFlagsChanged), cb, None)
        if tap is None:
            self._tap_ok = False; self._tap_ready.set(); return
        src = CFMachPortCreateRunLoopSource(None, tap, 0)
        CFRunLoopAddSource(CFRunLoopGetCurrent(), src, kCFRunLoopDefaultMode)
        CGEventTapEnable(tap, True)
        self._tap_ok = True; self._tap_ready.set()
        while not self._quit.is_set():
            NSRunLoop.currentRunLoop().runUntilDate_(
                NSDate.dateWithTimeIntervalSinceNow_(0.1))

    # ── Windows: pynput (Right Ctrl key) ──────────────────────────────────
    def _tap_thread_windows(self):
        # Reverse map: pynput Key → our key name
        _WIN_KEY_REV = {v: k for k, v in PTT_KEYS_WIN.items()}

        def _get_ptt():
            return PTT_KEYS_WIN.get(self.ptt_key, _pynput_kb.Key.ctrl_r)

        def on_press(key):
            try:
                # ── Capture mode ──
                if self._capture_mode and key in _WIN_KEY_REV:
                    name = _WIN_KEY_REV[key]
                    self._capture_mode = False
                    self.ptt_key = name
                    emit({"type": "ptt_key_captured", "key": name,
                          "display": PTT_KEY_DISPLAY.get(name, name)})
                    return

                if key == _get_ptt() and not self._fn_down:
                    now = time.time()
                    if now - self._fn_release_time < 0.15:
                        return
                    self._fn_down = True
                    threading.Thread(target=self._start_rec, daemon=True).start()
            except Exception:
                pass

        def on_release(key):
            try:
                if key == _get_ptt() and self._fn_down:
                    self._fn_down         = False
                    self._fn_release_time = time.time()
                    threading.Thread(target=self._stop_rec, daemon=True).start()
            except Exception:
                pass

        self._tap_ok = True
        self._tap_ready.set()
        with _pynput_kb.Listener(on_press=on_press, on_release=on_release) as lst:
            while not self._quit.is_set():
                time.sleep(0.1)
            lst.stop()

    # ── stdin command reader ───────────────────────────────────────────────
    def _cmd_thread(self):
        for line in sys.stdin:
            line = line.strip()
            if not line: continue
            try:
                cmd = json.loads(line)
                if cmd.get("cmd") == "set_lang":
                    self.lang = cmd.get("lang", self.lang)
                elif cmd.get("cmd") == "set_mode":
                    self.mode = cmd.get("mode", self.mode)
                elif cmd.get("cmd") == "set_ptt_key":
                    new_key = cmd.get("key", "")
                    valid = PTT_KEYS_MAC if PLATFORM == "Darwin" else PTT_KEYS_WIN
                    if new_key in valid:
                        self.ptt_key = new_key
                        emit({"type": "ptt_key_ack", "key": new_key,
                              "display": PTT_KEY_DISPLAY.get(new_key, new_key)})
                elif cmd.get("cmd") == "capture_ptt_key":
                    self._capture_mode = True
                    emit({"type": "ptt_capture_started"})
                elif cmd.get("cmd") == "quit":
                    self._quit.set()
                elif cmd.get("cmd") == "request_perm":
                    perm = cmd.get("perm", "")
                    targets = [perm] if perm != "all" else ["im", "ax"]
                    for p in targets:
                        if p == "im" and PLATFORM == "Darwin":
                            subprocess.Popen([
                                "open",
                                "x-apple.systempreferences:com.apple.preference.security?Privacy_ListenEvent"
                            ])
                            _request_im_prompt()
                        elif p == "ax" and PLATFORM == "Darwin":
                            subprocess.Popen([
                                "open",
                                "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility"
                            ])
                            _request_ax_prompt()
            except Exception:
                pass

    # ── Main ──────────────────────────────────────────────────────────────
    def run(self):
        if not HAS_AUDIO:
            emit({"type": "error", "msg": "sounddevice not installed"}); return

        if PLATFORM == "Darwin" and not HAS_OBJC:
            emit({"type": "error", "msg": "pyobjc not installed"}); return

        if PLATFORM == "Windows" and not HAS_PYNPUT:
            emit({"type": "error", "msg": "pynput / pyperclip not installed"}); return

        if PLATFORM == "Linux" and not HAS_PYNPUT:
            emit({"type": "error", "msg": "pynput not installed"}); return

        if PLATFORM == "Linux":
            # Check clipboard/paste tools are available
            missing = []
            if _LINUX_SESSION == "wayland":
                for cmd in ["wl-copy", "wl-paste"]:
                    if not shutil.which(cmd):
                        missing.append(cmd)
                if not (shutil.which("wtype") or shutil.which("ydotool") or shutil.which("xdotool")):
                    missing.append("wtype (or ydotool or xdotool)")
            else:
                if not shutil.which("xclip"):
                    missing.append("xclip")
                if not shutil.which("xdotool"):
                    missing.append("xdotool")
            if missing:
                emit({"type": "error",
                      "msg": f"Missing tools: {', '.join(missing)}. Run the install script or install them manually."})
                return

        # Instance lock — prevent double-paste from two running daemons
        if not _acquire_instance_lock():
            emit({"type": "error",
                  "msg": "Another Samvad is already running — quit it first."}); return

        emit({"type": "init", "has_key": bool(self.key)})

        # ── Start reading UI commands immediately (needed during perm phase) ──
        threading.Thread(target=self._cmd_thread, daemon=True).start()

        # ── Detect terminal app name for permission instructions ────────
        _term_app = os.environ.get("TERM_PROGRAM", "")
        _term_names = {
            "Apple_Terminal": "Terminal",
            "iTerm.app": "iTerm",
            "WarpTerminal": "Warp",
            "vscode": "Visual Studio Code",
            "alacritty": "Alacritty",
            "kitty": "kitty",
            "tmux": "tmux",
        }
        _term_display = _term_names.get(_term_app, _term_app or "your terminal app")

        # ── macOS: trigger permission prompts so Terminal appears in lists
        if PLATFORM == "Darwin":
            _request_im_prompt()
            _request_ax_prompt()

        # ── Start key tap (retry loop for macOS permissions) ──────────
        if PLATFORM == "Darwin":
            # Try to start the tap. If it fails (permissions not granted),
            # show permission instructions and keep retrying every 2s.
            _perm_start = time.time()
            while True:
                self._tap_ok = False
                self._tap_ready = threading.Event()
                t = threading.Thread(target=self._tap_thread_macos, daemon=True)
                t.start()
                self._tap_ready.wait(timeout=5.0)
                if self._tap_ok:
                    # Tap succeeded → Input Monitoring is granted.
                    # Now wait for Accessibility if not yet granted.
                    while not _has_ax():
                        stuck = (time.time() - _perm_start) > 10
                        emit({"type": "perm", "im": True, "ax": False, "stuck": stuck,
                              "terminal": _term_display})
                        time.sleep(1)
                    break
                # Tap failed — show permission screen and retry
                ax = _has_ax()
                stuck = (time.time() - _perm_start) > 10
                emit({"type": "perm", "im": False, "ax": ax, "stuck": stuck,
                      "terminal": _term_display})
                time.sleep(2)
            # All permissions granted
            emit({"type": "perm", "im": True, "ax": True, "stuck": False})
        else:
            threading.Thread(target=self._tap_thread_windows, daemon=True).start()
            self._tap_ready.wait(timeout=5.0)
            if not self._tap_ok:
                emit({"type": "error",
                      "msg": "Key listener failed — run as administrator (Windows) or check input group (Linux)."})
                return

        emit({"type": "ready", "lang": self.lang, "mode": self.mode,
              "has_key": bool(self.key),
              "ptt_key": PTT_KEY_DISPLAY.get(self.ptt_key, self.ptt_key)})

        signal.signal(signal.SIGINT,  lambda *_: self._quit.set())
        signal.signal(signal.SIGTERM, lambda *_: self._quit.set())
        self._quit.wait()


if __name__ == "__main__":
    Core().run()
