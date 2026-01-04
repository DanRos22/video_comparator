# Video Comparator

A PyQt6-based desktop application for **side-by-side video comparison** with pixel-level analysis, frame-by-frame navigation, and interactive zoom/pan controls.

## Features

### Core Functionality
- **Load & Compare Two Sources**
  - Video files: MP4, AVI, MOV, MKV, FLV, WMV
  - Folders of images: JPG, JPEG, PNG, BMP, TIFF, TIF, WEBP
  - Automatic frame synchronization

- **Three-Pane View**
  - **Left**: Reference frame (original)
  - **Middle**: Comparison frame (auto-resized to match reference dimensions)
  - **Right**: Difference view (color-coded: Black=no diff, Blue=small, Red=large)

### Playback & Navigation
- **Play/Pause** with spacebar or button
- **Frame Slider** for manual scrubbing (shows current/total frames)
- **Speed Control**: 0.1× to 5.0× (0.1× increments)
- **Loop Toggle**: Enable/disable auto-looping at end
- **Hide/Show Diff**: Toggle difference pane to improve performance

### Viewing Controls
- **Zoom**: 0.1× to 8.0×
  - Mouse wheel (scroll up/down)
  - Keyboard: `+` / `=` (zoom in), `-` (zoom out)
- **Pan**: Drag with left mouse button or arrow keys
  - `Left/Right/Up/Down` arrows for keyboard pan
  - Auto-constrained to prevent losing image
- **Rotation**: ±90° increments
  - `-90°` (counter-clockwise), `+90°` (clockwise), `Reset Rot` buttons
- **Fit Screen**: One-click reset zoom and center image

### Pixel Inspection
- **Hover-based pixel reading**: Move cursor over any viewer
- Real-time display of:
  - Exact pixel coordinates (x, y)
  - RGB values from reference image
  - RGB values from comparison image

### Additional Features
- **Swap L/R**: Instantly swap reference and comparison sources
- **Drag & Drop**: Drop videos/folders onto left (reference) or middle (comparison) viewer
- **Logging**: Detailed logs written to `logs/video_comparator.log`

## Installation

### Requirements
- Python 3.8+
- PyQt6
- OpenCV (cv2)
- NumPy

### Setup

```bash
# Clone or download the repository
git clone <repo-url>
cd video_comparator

# Install dependencies
pip install -r requirements.txt
```

### Run

```bash
python video_comparator.py
```

## Building Executable

### Using PyInstaller

```bash
# Single-file executable (recommended)
pyinstaller --onefile --windowed --icon=app_icon.ico --name=VideoComparator video_comparator.py

# Or use the spec file
pyinstaller video_comparator.spec
```

The executable will be created in the `dist/` folder.

## Usage

### Loading Videos/Folders
1. Click **Load Reference Video** or **Load Reference Folder** (left side)
2. Click **Load Comparison Video** or **Load Comparison Folder** (right side)
3. Or **drag and drop** files/folders directly onto the left (reference) or middle (comparison) viewer

### Playback
- Press **Spacebar** or click **▶ Play** to start/pause
- Use **Speed** slider to adjust playback rate (0.1× to 5.0×)
- Toggle **🔄 Loop** to enable/disable auto-looping
- Scrub frames with the **Frame Slider**

### Viewing
- **Zoom**: Scroll mouse wheel or press `+` / `-`
- **Pan**: Click and drag with left mouse button, or use arrow keys
- **Rotate**: Click rotation buttons or reset with **Reset Rot**
- **Fit Screen**: Click to auto-zoom to fit window

### Pixel Inspection
- Hover your cursor over any of the three viewers
- RGB values update in real-time at the bottom
- Shows coordinates and color values for both images

### Performance Tips
- For high-resolution videos, **hide the Difference View** using **Hide Diff** button
- This skips expensive difference calculations and improves playback smoothness
- Very long videos are automatically sampled (~300 frame limit for memory efficiency)

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play/Pause |
| `+` / `=` | Zoom in |
| `-` | Zoom out |
| `↑` `↓` `←` `→` | Pan up/down/left/right |

## Architecture

### Core Components

**VideoComparator**
- Handles video/image loading from files and folders
- Manages frame storage and retrieval
- Computes pixel-level differences (Chebyshev distance)
- Tracks reference and comparison frame data

**ImageViewer** (QLabel subclass)
- Custom widget for displaying frames
- Handles zoom/pan/rotation transformations
- Emits signals for mouse/keyboard interaction
- Accepts drag-and-drop file loading

**VideoComparatorApp** (QMainWindow)
- Main UI window
- Unified loader methods (DRY refactored):
  - `_show_and_load_source()` - dialog handling
  - `_load_source()` - universal file/folder detection
  - `_set_source_info()` - UI/state updates
  - `_reset_state_after_load()` - state reset
- Playback control and frame display pipeline
- Event filtering for global keyboard shortcuts

### Data Flow

```
User Action (button/keyboard/drag)
    ↓
Event Handler (_show_and_load_source / _load_from_drop)
    ↓
_load_source() - Auto-detects file vs folder
    ↓
VideoComparator.load_video() / load_images_from_folder()
    ↓
_set_source_info() - Update UI and comparator state
    ↓
_reset_state_after_load() - Reset zoom/pan/rotation
    ↓
on_frame_changed() - Display frames
    ↓
_apply_view_transform() - Apply rotation/zoom/pan
    ↓
_set_pixmap() - Render to Qt widgets
```

## Logging

Logs are written to `logs/video_comparator.log` with timestamps and debug information.

**Check logs for:**
- Video/folder load errors
- Frame timing information
- Performance diagnostics
- User actions (play, pause, load, etc.)

## Technical Details

### Difference Calculation
Uses **Chebyshev distance** (max of absolute differences across RGB channels):
- `diff = max(|R1-R2|, |G1-G2|, |B1-B2|) / 255.0`
- Visualized as:
  - **Black**: No difference (0.0)
  - **Blue**: Small difference (0.0 - 0.5)
  - **Red**: Large difference (0.5 - 1.0)

### Performance Optimizations
- **Frame Sampling**: Videos limited to ~300 frames to manage memory
- **Lazy Diff Calculation**: Only computed when diff pane is visible
- **Comparison Resize Skip**: Only resizes comparison frame when diff is computed
- **Efficient Transforms**: Uses OpenCV for rotation, numpy for zoom/pan
- **Contiguous Memory**: Ensures QImage compatibility for fast rendering

### Video Format Support
- **Container**: MP4, AVI, MOV, MKV, FLV, WMV
- **Image Formats**: JPG, JPEG, PNG, BMP, TIFF, TIF, WEBP
- All formats read via OpenCV (platform-dependent codec support)

## Refactoring (v1.1)

**Unified Loading Architecture**
- Consolidated 4 separate load methods into 1 universal `_load_source()`
- Auto-detects file vs folder, video vs images
- 75% reduction in duplicated code
- Single source of truth for all loading logic

**Rotation Logic Refactored**
- Extracted `_reset_pan_and_refresh()` shared helper
- Used by `rotate_left()`, `rotate_right()`, `reset_rotation()`
- Eliminates pan reset duplication

## Troubleshooting

### No frames displayed
- Check `logs/video_comparator.log` for load errors
- Verify video format is supported (MP4, AVI, MOV, MKV)
- For image folders, ensure files have valid extensions (.jpg, .png, etc.)

### Choppy playback
- **Hide the Difference View** (click "Hide Diff")
- Disable comparison frame resize (only happens when diff is visible)
- Try lower resolution source videos
- Check system CPU/memory usage

### Spacebar doesn't work
- Click on the window to ensure it has focus
- Check that no buttons are currently focused
- The spacebar is mapped as a global hotkey via event filter

### Icons not showing
- Optional feature; app works without icons
- If building executable, include `app_icon.ico` in same folder

## Future Enhancements
- Multi-frame difference timeline graph
- Export frame comparisons as images
- Color channel separation view
- Benchmark/metrics overlay
- Video export (overlay/diff visualization)

## License

MIT License - Feel free to modify and distribute

## Contributing

Pull requests welcome! Focus areas:
- Additional video codec support
- Performance optimization
- UI/UX improvements
- Bug fixes
