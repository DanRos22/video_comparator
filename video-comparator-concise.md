# Video Comparator (PyQt6) – Concise Overview

## Purpose

Desktop tool to **visually compare two videos or image sequences** side‑by‑side with a per‑pixel difference view and interactive inspection.[file:2]

---

## Features

- Load **reference** and **comparison**:
  - Video files: `*.mp4`, `*.avi`, `*.mov`, `*.mkv`.[file:2]
  - Image folders: common formats (`.jpg`, `.png`, `.bmp`, `.tiff`, `.webp`).[file:2]
- Side‑by‑side viewers:
  - Left: Reference frame.
  - Middle: Comparison frame (resized to match reference).
  - Right: Color‑coded diff (black = 0, blue = small, red = large).[file:2]
- Frame navigation:
  - Slider with current/total frame index display.
  - Playback with speed control (0.1x–5.0x) and loop toggle.[file:2]
- View controls:
  - Zoom range ~0.1x–8.0x (mouse wheel or `+` / `-` keys).[file:2]
  - Pan via mouse drag or arrow keys.[file:2]
  - Rotation: −90°, +90°, reset.[file:2]
  - “Fit Screen” to auto‑fit reference into the left viewer.[file:2]
- Diff controls:
  - “Hide Diff” / “Show Diff” button:
    - Hides/shows the right diff panel.
    - Skips diff computation when hidden for performance.[file:2]
- Pixel inspection:
  - Hover over any viewer to see:
    - Position `(x, y)`.
    - RGB values in reference and comparison at that pixel.[file:2]
- Swap:
  - Swap reference/comparison content and titles (L/R swap).[file:2]
- Logging:
  - Writes detailed logs to `logs/video_comparator.log`.[file:2]

---

## How It Works (Core Logic)

- **Frame loading**:
  - Videos: sampled up to ~300 frames to limit memory; frames converted BGR→RGB.[file:2]
  - Folders: sorted by filename; all readable images loaded at original size.[file:2]
- **Synchronization**:
  - Frame index is shared between reference and comparison; the diff uses the same index.[file:2]
- **Resizing**:
  - Comparison frame is resized to reference `width × height` before diff and display.[file:2]
- **Diff computation** (when enabled):
  - `diff_uint = abs(ref - comp_resized)` in `uint8`.[file:2]
  - `mag = max(diff_uint over RGB) / 255` → [0, 1].[file:2]
  - Diff image:
    - Red channel = `mag * 255`.
    - Blue channel = `(1 - mag) * 255`.
    - Green channel = 0.[file:2]
- **View transform**:
  - Rotation (0/90/180/270) applied first.
  - Custom zoom/pan:
    - Computes a centered crop according to `zoom`, `pan_x`, `pan_y`.
    - Clamps pan to keep crop inside image bounds.
    - Resizes crop to viewer size (`left_view.height() × left_view.width()`).
    - Ensures contiguous array for `QImage`.[file:2]

---

## Controls (User Interaction)

- Mouse:
  - Wheel: zoom in/out on active viewer.
  - Left‑drag: pan when pressed.
  - Hover: live pixel info (no click needed).[file:2]
- Keyboard:
  - `+` / `=`: zoom in.
  - `-`: zoom out.
  - Arrow keys: pan in corresponding direction.[file:2]
- Buttons:
  - File: load ref/comp video or folder.
  - Playback: Play/Pause, Loop ON/OFF, Speed spinner.[file:2]
  - View: Fit Screen, Rotate −90° / +90°, Reset Rotation, Swap L/R, Hide/Show Diff.[file:2]

---

## Build & Run

- Requirements:
  - `PyQt6`, `opencv-python`, `numpy`, `pyinstaller`.[file:2]
- Run as script:
  - `python video_comparator.py`.[file:2]
- Build executable (examples):
  - `pyinstaller --onefile --windowed --icon=app_icon.ico --name=VideoComparator video_comparator.py`.[file:2]
