# Samvad — Voice to Text for macOS & Windows

Hold `fn` (macOS) or `Right Ctrl` (Windows) anywhere → speak → release → text pastes at your cursor.

## Install

### macOS (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.sh | bash
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

### Windows (two commands)

Open **Command Prompt** and run these **one after the other**:

**Step 1** — allow scripts to run (one time only):
```
powershell -c "Set-ExecutionPolicy RemoteSigned -Scope CurrentUser -Force"
```

**Step 2** — install Samvad:
```
powershell -c "iwr -useb https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.ps1 | iex"
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

- macOS or Windows
- Internet connection (for transcription via Sarvam AI)
