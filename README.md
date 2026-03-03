# Samvad — Voice to Text for macOS

Hold `fn` anywhere → speak → release → text pastes at your cursor.

## Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/mrunalpendem123/samvad-terminal/main/install.sh | bash
```

Then run:

```bash
samvad
```

## First Run

macOS will ask for permissions — go to **System Settings → Privacy & Security** and enable Terminal for:
- **Accessibility**
- **Input Monitoring**

Then run `samvad` again.

## Controls

| Key | Action |
|-----|--------|
| Hold `fn` | Start recording |
| Release `fn` | Transcribe & paste |
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

- macOS only
- Internet connection (for transcription via Sarvam AI)
