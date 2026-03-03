#!/usr/bin/env python3
"""
samvad-core — Python backend. No UI.
Communicates with samvad-ui.ts via JSON lines on stdio.
stdin  ← commands from UI  (set_lang, set_mode, quit)
stdout → status messages to UI
"""
from __future__ import annotations
import ctypes, fcntl, io, json, os, re, signal, subprocess, sys
import threading, time, wave
from datetime import datetime
from pathlib import Path

# System-wide lock files (prevent multiple instances / cross-process double-paste)
_INSTANCE_LOCK = Path("/tmp/.samvad_instance.lock")
_PASTE_LOCK    = Path("/tmp/.samvad_paste.lock")

import requests

try:
    import sounddevice as sd
    import numpy as np
    HAS_AUDIO = True
except ImportError:
    HAS_AUDIO = False

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
    HAS_OBJC = False

# ── macOS permissions ──────────────────────────────────────────────────────────
_ax = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices")
_cg = ctypes.cdll.LoadLibrary(
    "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
_ax.AXIsProcessTrusted.restype             = ctypes.c_bool
_ax.AXIsProcessTrustedWithOptions.restype  = ctypes.c_bool
_ax.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]
_cg.CGPreflightListenEventAccess.restype   = ctypes.c_bool
_cg.CGRequestListenEventAccess.restype     = ctypes.c_bool

def _has_ax(): return bool(_ax.AXIsProcessTrusted())
def _has_im(): return bool(_cg.CGPreflightListenEventAccess())

FN_FLAG = 0x800000

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
              Path.home() / "Desktop" / "sarvam" / "backend" / ".env"]:
        if p.exists():
            for line in p.read_text().splitlines():
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


# ── Core ───────────────────────────────────────────────────────────────────────
class Core:
    def __init__(self):
        self.key      = _load_key()
        self.lang     = "en-IN"
        self.mode     = "direct"
        self._quit    = threading.Event()
        self._stop    = threading.Event()
        self._frames  : list = []
        self._lock    = threading.Lock()
        self._tx_lock = threading.Lock()   # prevents concurrent transcription/paste
        self._fn_down = False
        self._fn_release_time = 0.0        # debounce: time of last fn release
        self._tap_ready = threading.Event()
        self._tap_ok    = False
        self._recording = False

    def _lang_name(self):
        return LANG_MAP.get(self.lang, (self.lang, self.lang))[1]

    # ── WAV helper ────────────────────────────────────────────────────
    def _wav(self, pcm: bytes) -> bytes:
        b = io.BytesIO()
        with wave.open(b, "wb") as wf:
            wf.setnchannels(1); wf.setsampwidth(2)
            wf.setframerate(16000); wf.writeframes(pcm)
        return b.getvalue()

    # ── ASR ───────────────────────────────────────────────────────────
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

    # ── Translate ─────────────────────────────────────────────────────
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

    # ── Polish ────────────────────────────────────────────────────────
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

    # ── Recording ─────────────────────────────────────────────────────
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

    # ── Transcription + paste ─────────────────────────────────────────
    def _tx_thread(self):
        # Only one transcription/paste may run at a time
        if not self._tx_lock.acquire(blocking=False):
            return
        try:
            # Snapshot frames immediately and clear so a racing thread gets nothing
            frames, self._frames = self._frames, []
            if not frames:
                emit({"type": "status", "status": "idle"}); return

            # Discard recordings shorter than 300 ms (keyboard bounce / accidental tap)
            duration_s = len(frames) * 1024 / 16000
            if duration_s < 0.3:
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

            # Cross-process paste lock — if another samvad instance is already
            # pasting, skip this paste entirely to prevent double-paste.
            paste_fd = open(_PASTE_LOCK, "w")
            try:
                fcntl.flock(paste_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                paste_fd.close()
                emit({"type": "status", "status": "idle"}); return
            try:
                subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
                time.sleep(0.08)
                subprocess.run(["osascript", "-e",
                    'tell application "System Events" to keystroke "v" using command down'],
                    check=True)
                time.sleep(1.0)   # hold lock 1 s so a second instance can't sneak in
            finally:
                fcntl.flock(paste_fd, fcntl.LOCK_UN)
                paste_fd.close()

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

    # ── CGEventTap (fn key) ───────────────────────────────────────────
    def _tap_thread(self):
        def cb(proxy, etype, event, refcon):
            try:
                if etype == kCGEventFlagsChanged:
                    fn  = bool(CGEventGetFlags(event) & FN_FLAG)
                    now = time.time()
                    if fn and not self._fn_down:
                        # Debounce: ignore re-press within 300 ms of last release
                        if now - self._fn_release_time < 0.3:
                            return event
                        self._fn_down = True
                        threading.Thread(target=self._start_rec, daemon=True).start()
                    elif not fn and self._fn_down:
                        self._fn_down        = False
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

    # ── stdin command reader ──────────────────────────────────────────
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
                elif cmd.get("cmd") == "quit":
                    self._quit.set()
            except Exception:
                pass

    # ── Main ──────────────────────────────────────────────────────────
    def run(self):
        if not HAS_AUDIO:
            emit({"type": "error", "msg": "sounddevice not installed"}); return
        if not HAS_OBJC:
            emit({"type": "error", "msg": "pyobjc not installed"}); return

        # Prevent multiple instances — grab exclusive lock on instance file
        self._instance_fd = open(_INSTANCE_LOCK, "w")
        try:
            fcntl.flock(self._instance_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            emit({"type": "error",
                  "msg": "Another Samvad is already running — quit it first (Ctrl+C)."})
            return

        emit({"type": "init", "has_key": bool(self.key)})

        # Permission loop
        _cg.CGRequestListenEventAccess()
        if HAS_OBJC:
            try:
                opts = NSDictionary.dictionaryWithObject_forKey_(
                    NSNumber.numberWithBool_(True), "AXTrustedCheckOptionPrompt")
                _ax.AXIsProcessTrustedWithOptions(ctypes.c_void_p(id(opts)))
            except Exception:
                pass

        while not (_has_ax() and _has_im()):
            emit({"type": "perm", "im": _has_im(), "ax": _has_ax()})
            time.sleep(2)

        emit({"type": "perm", "im": True, "ax": True})

        # Start CGEventTap
        threading.Thread(target=self._tap_thread, daemon=True).start()
        self._tap_ready.wait(timeout=5.0)
        if not self._tap_ok:
            emit({"type": "error", "msg": "CGEventTap failed — grant Accessibility in System Settings"})
            return

        emit({"type": "ready", "lang": self.lang, "mode": self.mode, "has_key": bool(self.key)})

        # stdin reader
        threading.Thread(target=self._cmd_thread, daemon=True).start()

        signal.signal(signal.SIGINT,  lambda *_: self._quit.set())
        signal.signal(signal.SIGTERM, lambda *_: self._quit.set())
        self._quit.wait()


if __name__ == "__main__":
    Core().run()
