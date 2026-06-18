# Clipboard Image Saver

A dark-themed Windows system tray application that automatically saves images from your clipboard as PNG files — and copies the file path back to your clipboard for instant pasting.

![UI Preview](https://img.shields.io/badge/UI-Dark%20Blue-89b4fa)
![Python](https://img.shields.io/badge/Python-3.13-3776AB)
![PyQt5](https://img.shields.io/badge/PyQt5-5.15-41CD52)

---

## Quick Start (End User)

### Run the `.exe`

1. Double-click **`ClipboardSaver.lnk`** (shortcut in the project root).
   > Or navigate to `ClipboardSaver/ClipboardSaver.exe` and run it directly.
2. The window opens immediately. Close the window to **minimize to tray** (it keeps running).
3. To exit completely: right-click the tray icon → **Quit**.

### What happens when you copy an image

1. Copy any image to the clipboard (Ctrl+C from a browser, screenshot tool, image editor, etc.)
2. The app **automatically** saves it as a `.png` in `ClipboardSaver/screenshots/`.
3. The **file path** (`file:///...`) is placed back into your clipboard.
4. You can immediately paste the path anywhere (Ctrl+V into a chat, editor, file dialog, etc.).
5. Each new image **replaces** the previous one — only one screenshot is kept at any time.

### Manual save (Ctrl+V in the app)

Click **Paste (Ctrl+V)** or press the keyboard shortcut — works the same way as the automatic save, but triggered on demand.

### Copy file path (Ctrl+C in the app)

If you need the path of the last saved screenshot again, click **Copy (Ctrl+C)** or press the keyboard shortcut.

### Tray menu

| Action | How |
|---|---|
| Show window | Double-click tray icon |
| Hide to tray | Close the window |
| Quit app | Right-click tray icon → Quit |

---

## Application Structure

```
ClipboardSaver.lnk          ← desktop shortcut
ClipboardSaver/
├── ClipboardSaver.exe      ← standalone executable (~58 MB)
├── screenshots/            ← saved PNG images (max 1 file)
└── clipboard_saver.log     ← rotating log (3 × 1 MB)
```

No console window appears — the app runs silently in the background.

---

## Developer Guide

### Prerequisites

- Python 3.13+
- pip

### Install dependencies

```bash
pip install PyQt5 Pillow pyinstaller
```

### Run the script directly

```bash
cd "clipboard-image-saver-main"
python main.py
```

Screenshots are saved to `./screenshots/` and logs to `./clipboard_saver.log`.

### Build the `.exe` yourself

```bash
pyinstaller --noconsole --onefile --name ClipboardSaver ^
    --hidden-import PyQt5.QtCore ^
    --hidden-import PyQt5.QtGui ^
    --hidden-import PyQt5.QtWidgets ^
    --hidden-import PIL ^
    --hidden-import PIL.Image ^
    --hidden-import PIL.ImageDraw ^
    main.py
```

The output is `dist/ClipboardSaver.exe` (~50–60 MB). Deploy into any folder; the app creates `screenshots/` and the log file next to the `.exe`.

### Use the clipboard monitor in your own project

The core logic lives in the `ClipboardSaver` class (`main.py`). It is a `QWidget` subclass and can be embedded or instantiated programmatically.

#### Minimal integration example

```python
import sys
from PyQt5.QtWidgets import QApplication
from main import ClipboardSaver

app = QApplication(sys.argv)
win = ClipboardSaver()
win.show()
sys.exit(app.exec_())
```

#### Key APIs

| Method | Description |
|---|---|
| `handle_paste()` | Save current clipboard image manually |
| `refresh_preview()` | React to clipboard change (connected to `QClipboard.dataChanged`) |
| `show_image(qimage)` | Display a `QImage` in the preview widget |
| `last_saved_path` | `str` — path to the last saved file, or `None` |
| `clipboard` | `QClipboard` instance (useful for `clipboard.image()` / `clipboard.mimeData()`) |

#### Signals to watch

- `QApplication.clipboard().dataChanged` — fires on every clipboard change
- `QTimer.singleShot(500, ...)` — deferred processing inside `_process_clipboard()`

#### Customization points

- **Save directory**: change `self.save_dir` in `__init__`
- **File format**: change `"PNG"` in `qimg.save(path, "PNG")` to `"BMP"`, `"JPEG"`, etc.
- **Deferred delay**: change `500` in `QTimer.singleShot(500, self._process_clipboard)`
- **Auto-delete previous**: controlled by `if self.last_saved_path and os.path.exists(self.last_saved_path)` blocks in `handle_paste()` and `_process_clipboard()`

#### Path resolution

The `BASE` variable determines where `screenshots/` and the log file are created:

```python
if getattr(sys, 'frozen', False):
    BASE = os.path.dirname(sys.executable)   # .exe location
else:
    BASE = os.path.dirname(os.path.abspath(__file__))  # script location
```

### Theme customization

Colors are defined in `_apply_theme()` as a single `QStyleSheet` string. The palette is based on [Catppuccin Mocha](https://github.com/catppuccin/catppuccin):

| Token | Color | Usage |
|---|---|---|
| Background | `#1e1e2e` | Main window |
| Surface | `#2b2b3d` | Preview area |
| Accent | `#89b4fa` | Buttons, icons |
| Accent hover | `#74c7ec` | Button hover |
| Danger | `#f38ba8` | Close button hover |
| Text | `#cdd6f4` | Primary text |
| Muted | `#a6adc8` | Secondary text |
| Border | `#45475a` | Preview border |

---

## Technical Details

- **Framework**: PyQt5 (Qt 5.15)
- **Image processing**: Pillow (for test image generation)
- **Packaging**: PyInstaller 6.13 — single-file `.exe`, no console
- **Window**: Frameless custom title bar with Aero Snap support
- **Clipboard**: Uses `QClipboard` with `dataChanged` signal and deferred processing (500 ms) to avoid race conditions
- **Logging**: `RotatingFileHandler` — max 1 MB per file, 3 backups
- **System tray**: `QSystemTrayIcon` with context menu

### Platform

Tested on **Windows 10/11** only. PyQt5 clipboard behavior varies across platforms — macOS and Linux may need adjustments.
