# Samvad — Voice to Text for macOS, Windows & Linux

Hold `fn` (macOS) or `Right Ctrl` (Windows/Linux) anywhere → speak → release → text pastes at your cursor.

## Install

### macOS

```bash
curl -fsSL https://tinyurl.com/2a86ls55 | bash
```

Then run:

```bash
samvad
```

**First run:** macOS will ask for permissions — go to **System Settings → Privacy & Security** and enable Terminal for:
- **Accessibility**
- **Input Monitoring**

Then run `samvad` again.

---

### Linux

Works on **Ubuntu**, **Debian**, **Fedora**, **Arch**, **openSUSE**, **Mint**, **Pop!_OS**, **Manjaro**, **Elementary**, and other Linux distros. Supports both **X11** and **Wayland**.

```bash
curl -fsSL https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.sh | bash
```

Then run:

```bash
samvad
```

**First run:** If key listening fails, add your user to the `input` group:

```bash
sudo usermod -aG input $USER
```

Then **log out and back in**, and run `samvad` again.

#### System dependencies

The installer auto-detects your package manager (apt, dnf, pacman, zypper, apk) and installs:

| Package | Purpose |
|---------|---------|
| `portaudio` | Audio capture from microphone |
| `gtk3` + `python3-gi` | Floating overlay indicator |
| **X11:** `xclip` + `xdotool` | Clipboard access + simulating Ctrl+V |
| **Wayland:** `wl-clipboard` + `wtype` | Clipboard access + simulating Ctrl+V |

<details>
<summary>Manual install (if auto-detect fails)</summary>

**Ubuntu / Debian:**
```bash
sudo apt install portaudio19-dev python3-gi python3-gi-cairo gir1.2-gtk-3.0
# X11:
sudo apt install xclip xdotool
# Wayland:
sudo apt install wl-clipboard wtype
```

**Fedora:**
```bash
sudo dnf install portaudio-devel python3-gobject gtk3
# X11:
sudo dnf install xclip xdotool
# Wayland:
sudo dnf install wl-clipboard wtype
```

**Arch / Manjaro:**
```bash
sudo pacman -S portaudio python-gobject gtk3
# X11:
sudo pacman -S xclip xdotool
# Wayland:
sudo pacman -S wl-clipboard wtype
```

**openSUSE:**
```bash
sudo zypper install portaudio-devel python3-gobject gtk3-devel
# X11:
sudo zypper install xclip xdotool
# Wayland:
sudo zypper install wl-clipboard wtype
```
</details>

---

### Windows

Open **Command Prompt** and run these **one after the other**:

**Step 1** — allow scripts (one time only):
```
powershell -c "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force"
```

**Step 2** — install Samvad:
```
powershell -c "iwr -useb https://tinyurl.com/282r66ke | iex"
```

Open a **new** terminal, then run:

```
samvad
```

**First run:** Windows may ask for input-monitoring permissions — allow when prompted.

---

## Controls

| Key | Action |
|-----|--------|
| Hold `fn` / `Right Ctrl` | Start recording |
| Release | Transcribe & paste |
| `S` | Settings (language / mode) |
| `H` | History |
| `L` | Cycle language |
| `M` | Cycle mode |
| `Esc` | Dismiss |
| `Ctrl+C` | Quit |

## Languages

English, Hindi, Hinglish→English, Tamil, Telugu, Malayalam, Kannada, Marathi, Gujarati, Bengali, Punjabi, Odia

## Modes

- **Direct** — transcribe as spoken
- **→ English** — translate to English
- **Polish** — AI clean-up (fix punctuation, remove fillers)

## Requirements

- macOS, Windows, or Linux (X11 or Wayland)
- Internet connection (for transcription via Sarvam AI)
