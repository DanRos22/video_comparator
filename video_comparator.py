"""
Video Comparator - PyQt6 Application
Compare two video streams side-by-side with pixel-level analysis.

Features:
- Load and compare reference vs comparison videos
- Frame-by-frame navigation with slider
- Zoom (0.1x to 8.0x) and pan with mouse/keyboard
- Image rotation (90° increments)
- Video playback with adjustable speed and loop toggle
- RGB pixel value inspection (hover-based, real-time)
- Left/right swap functionality
- Drag-and-drop video/folder loading
- Logging to video_comparator.log

Requirements:
    pip install PyQt6 opencv-python numpy pyinstaller

Build executable:
    pyinstaller --onefile --windowed --icon=app_icon.ico --name=VideoComparator video_comparator.py
    pyinstaller video_comparator.spec
"""

import os.path
import sys
from typing import Any
import os
import time

import cv2
import numpy as np
import logging
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSlider, QLabel, QFileDialog, QMessageBox, QDoubleSpinBox, QSplitter
)

from PyQt6.QtCore import Qt, pyqtSignal, QPoint, QTimer, QEvent, QUrl
from PyQt6.QtGui import QPixmap, QImage, QFont, QIcon, QDragEnterEvent, QDropEvent
from cv2 import Mat
from numpy import dtype, floating, integer, ndarray
# from numpy._core.multiarray import _SCT

# ============================================================================
# LOGGING SETUP
# ============================================================================

def get_app_dir() -> Path:
    # If running as PyInstaller EXE, sys.frozen is set
    if getattr(sys, "frozen", False):
        # Folder containing the EXE
        return Path(sys.executable).parent
    # Normal Python run: folder of the main script
    return Path(__file__).resolve().parent

def setup_logging():
    app_dir = get_app_dir()
    log_dir = app_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "video_comparator.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, mode='w', encoding="utf-8"),
            logging.StreamHandler()  # optional, for console runs
        ],
        force=True,
    )

    logging.getLogger(__name__).info("Logging initialized at %s", log_file)

# ============================================================================
# VIDEO LOADER & COMPARATOR
# ============================================================================

class VideoComparator:
    """Handles video/image loading and frame-level comparison."""

    def __init__(self):
        self.ref_frames = []
        self.comp_frames = []
        self.ref_info = None
        self.comp_info = None
        self.current_frame_idx = 0

    def load_video(self, video_path: str):
        """Load video and extract frames (limited to ~300 frames for performance)."""
        if not video_path or not Path(video_path).exists():
            logger.error(f"Video path invalid or doesn't exist: {video_path}")
            return None

        cap = cv2.VideoCapture(str(video_path))
        if not cap.isOpened():
            logger.error(f"Failed to open video: {video_path}")
            return None

        frames = []
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        step = max(1, n // 300)  # Sample frames to limit memory usage

        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if i % step == 0:
                frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            i += 1

        cap.release()
        logger.info(f"Loaded video: {video_path} - {w}x{h}, {len(frames)} frames")
        return {"frames": frames, "width": w, "height": h, "count": len(frames)}

    '''
    def _load_video_folder(self, video_path: str):
        """Load video folder"""
        from glob import glob
        from imageio import v3 as iio3
        def get_imgs_from_dir(folder, glob_key="*.png", known_len=0) -> np.array:
            fpaths = sorted(glob(os.path.join(folder, glob_key)))
            if known_len > 0:
                assert len(fpaths) == known_len
            return np.asarray(multi_thread(iio3.imread, fpaths))
        frames = []
        h, w = 0, 0
        return {"frames": frames, "width": w, "height": h, "count": len(frames)}
    '''

    def load_images_from_folder(self, folder_path: str):
        """Load images from a folder (sorted alphabetically)."""
        if not folder_path or not Path(folder_path).exists():
            logger.error(f"Folder path invalid or doesn't exist: {folder_path}")
            return None

        # Supported image extensions
        image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'}

        # Get all image files and sort them
        image_files = []
        for filename in sorted(os.listdir(folder_path)):
            if Path(filename).suffix.lower() in image_extensions:
                image_files.append(os.path.join(folder_path, filename))

        if not image_files:
            logger.error(f"No image files found in folder: {folder_path}")
            return None

        frames = []
        w, h = None, None

        for img_path in image_files:
            img = cv2.imread(img_path)
            if img is None:
                logger.warning(f"Failed to read image: {img_path}")
                continue

            # Get dimensions from first image
            if w is None:
                h_img, w_img, _ = img.shape
                w, h = w_img, h_img

            # Convert BGR to RGB
            rgb_img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            frames.append(rgb_img)

        if not frames:
            logger.error(f"No valid images loaded from folder: {folder_path}")
            return None

        logger.info(f"Loaded {len(frames)} images from folder: {folder_path} - {w}x{h}")
        return {"frames": frames, "width": w, "height": h, "count": len(frames)}

    def set_ref(self, info):
        """Set reference video frames."""
        self.ref_frames = info["frames"]
        self.ref_info = info

    def set_comp(self, info):
        """Set comparison video frames."""
        self.comp_frames = info["frames"]
        self.comp_info = info

    def frame_count(self):
        """Return number of common frames (minimum of both videos)."""
        if not (self.ref_frames and self.comp_frames):
            return 0
        return min(len(self.ref_frames), len(self.comp_frames))

    def get_frame_triplet(self, idx: int, compute_diff: bool = True):
        """Get reference, comparison, and optional difference frames at index."""
        if self.frame_count() == 0:
            return None, None, None

        idx = max(0, min(self.frame_count() - 1, int(idx)))
        self.current_frame_idx = idx

        ref = self.ref_frames[idx]
        comp_raw = self.comp_frames[idx]

        # Resize comparison to match reference dimensions (only if needed)
        if comp_raw.shape[:2] != (self.ref_info["height"], self.ref_info["width"]):
            comp_resized = cv2.resize(
                comp_raw,
                (self.ref_info["width"], self.ref_info["height"]),
                interpolation=cv2.INTER_LINEAR,
            )
        else:
            comp_resized = comp_raw

        if not compute_diff:
            return ref, comp_resized, None

        # Fast difference calculation using uint8 math (Chebyshev distance)
        diff_uint = cv2.absdiff(ref, comp_resized)
        mag = np.max(diff_uint, axis=2).astype(np.float32) / 255.0
        mag = np.clip(mag, 0.0, 1.0)

        h, w = ref.shape[:2]
        diff_rgb = np.zeros((h, w, 3), dtype=np.uint8)
        diff_rgb[:, :, 0] = (mag * 255).astype(np.uint8)        # Red channel
        diff_rgb[:, :, 2] = ((1.0 - mag) * 255).astype(np.uint8)  # Blue channel

        return ref, comp_resized, diff_rgb

    def get_pixel_info(self, x: int, y: int):
        """Get RGB values at (x, y) for both reference and comparison."""
        if not self.ref_info:
            return None
        if not (0 <= x < self.ref_info["width"] and 0 <= y < self.ref_info["height"]):
            return None

        ref = self.ref_frames[self.current_frame_idx]
        comp_raw = self.comp_frames[self.current_frame_idx]
        if comp_raw.shape[:2] != (self.ref_info["height"], self.ref_info["width"]):
            comp_resized = cv2.resize(
                comp_raw,
                (self.ref_info["width"], self.ref_info["height"]),
                interpolation=cv2.INTER_LINEAR,
            )
        else:
            comp_resized = comp_raw

        r1, g1, b1 = ref[y, x].tolist()
        r2, g2, b2 = comp_resized[y, x].tolist()
        return {
            "x": x,
            "y": y,
            "img1": (int(r1), int(g1), int(b1)),
            "img2": (int(r2), int(g2), int(b2)),
        }


# ============================================================================
# IMAGE VIEWER WIDGET
# ============================================================================

class ImageViewer(QLabel):
    """Custom QLabel for displaying images with zoom/pan/pixel hover support."""

    zoom_requested = pyqtSignal(float)
    pan_requested = pyqtSignal(int, int)
    pixel_hovered = pyqtSignal(int, int)
    files_dropped = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self.setScaledContents(False)
        self.setMinimumSize(400, 300)
        self.setStyleSheet("border: 1px solid #ccc; background: #000;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._dragging = False
        self._last_pos = QPoint()
        self.zoom_delta = 0.1
        # CRITICAL: Enable mouse tracking for hover events without button press
        self.setMouseTracking(True)
        # Enable drag-drop on this widget
        self.setAcceptDrops(True)

    def mousePressEvent(self, event):
        """Handle mouse press for pan start."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._last_pos = event.position().toPoint()
            # self._emit_pixel(event.position().toPoint())

    def mouseMoveEvent(self, event):
        """Handle mouse drag for panning OR emit pixel coordinates on hover."""
        if self._dragging:
            # Pan logic
            current = event.position().toPoint()
            dx = current.x() - self._last_pos.x()
            dy = current.y() - self._last_pos.y()
            self._last_pos = current
            self.pan_requested.emit(-dx, -dy)  # Invert for intuitive panning
        else:
            # On hover (not dragging): only emit if mouse is within widget
            pos = event.position().toPoint()
            if 0 <= pos.x() < self.width() and 0 <= pos.y() < self.height():
                self._emit_pixel(pos)
            # self._emit_pixel(event.position().toPoint())

    def mouseReleaseEvent(self, event):
        """Handle mouse release to end panning."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming."""
        delta = event.angleDelta().y()
        if delta > 0:
            self.zoom_requested.emit(+self.zoom_delta)
        elif delta < 0:
            self.zoom_requested.emit(-self.zoom_delta)

    def dragEnterEvent(self, event: QDragEnterEvent):
        """Accept drag if it contains file URLs."""
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        """Handle dropped files and emit signal."""
        urls = event.mimeData().urls()
        file_paths = [url.toLocalFile() for url in urls]
        self.files_dropped.emit(file_paths)
        event.acceptProposedAction()

    def _emit_pixel(self, pos: QPoint):
        """Convert widget-space coordinates to image-space and emit pixel hover."""
        if not self.pixmap():
            return

        pm = self.pixmap()
        img_w = pm.width()
        img_h = pm.height()

        # Guard: skip if pixmap has no dimensions (initialization or no image loaded)
        if img_w == 0 or img_h == 0:
            return

        lbl_w = self.width()
        lbl_h = self.height()

        # Calculate scaling factor (pixmap fitted to label)
        scale = min(lbl_w / img_w, lbl_h / img_h)
        disp_w = img_w * scale
        disp_h = img_h * scale
        offset_x = (lbl_w - disp_w) / 2
        offset_y = (lbl_h - disp_h) / 2

        # Convert to image coordinates
        x = (pos.x() - offset_x) / scale
        y = (pos.y() - offset_y) / scale

        # Only emit if within image bounds
        if 0 <= x < img_w and 0 <= y < img_h:
            self.pixel_hovered.emit(int(x), int(y))


# ============================================================================
# MAIN APPLICATION
# ============================================================================

class VideoComparatorApp(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()

        # Set window icon
        icon_path = Path(__file__).parent / "app_icon.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        # Application state
        self.comparator = VideoComparator()
        self.ref_path = ""
        self.comp_path = ""
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.rotation_angle = 0
        self.is_playing = False
        self.loop_enabled = True

        # Playback timer
        self.playback_timer = QTimer()
        self.playback_timer.timeout.connect(self.advance_frame)

        # state for diff visibility
        self.diff_visible = True

        self._zoom_buffer = None
        self._zoom_buffer_shape = None

        # Set focus policy so main window captures keys
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        # Install event filter for spacebar handling
        self.installEventFilter(self)

        logger.info("Application initialized")
        self.init_ui()

    @property
    def zoom_delta(self):
        return np.clip(self.zoom / 10, min=0.1, max=0.4)

    def eventFilter(self, obj, event):
        """Intercept events before widgets process them."""
        if event.type() == QEvent.Type.KeyPress:
            key = event.key()
            if key == Qt.Key.Key_Space:
                self.toggle_play()
                return True  # Consume the event
        return super().eventFilter(obj, event)

    def init_ui(self):
        """Initialize UI components."""
        self.setWindowTitle("Video Comparator")
        self.setGeometry(100, 100, 1400, 950)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout()

        # --- FILE SELECTION ROW ---
        file_layout = QHBoxLayout()

        # Reference video/folder buttons
        ref_btn_layout = QVBoxLayout()
        self.ref_btn = QPushButton("Load Reference Video")
        self.ref_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ref_btn.clicked.connect(lambda: self._show_and_load_source('video', is_reference=True))
        self.ref_folder_btn = QPushButton("Load Reference Folder")
        self.ref_folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.ref_folder_btn.clicked.connect(lambda: self._show_and_load_source('folder', is_reference=True))
        ref_btn_layout.addWidget(self.ref_btn)
        ref_btn_layout.addWidget(self.ref_folder_btn)

        self.ref_label = QLabel("No reference video/folder loaded")
        self.ref_label.setFont(QFont("Courier New", 9))
        self.ref_label.setWordWrap(True)

        file_layout.addLayout(ref_btn_layout)
        file_layout.addWidget(self.ref_label, 1)

        # Comparison video/folder buttons
        comp_btn_layout = QVBoxLayout()
        self.comp_btn = QPushButton("Load Comparison Video")
        self.comp_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.comp_btn.clicked.connect(lambda: self._show_and_load_source('video', is_reference=False))
        self.comp_folder_btn = QPushButton("Load Comparison Folder")
        self.comp_folder_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.comp_folder_btn.clicked.connect(lambda: self._show_and_load_source('folder', is_reference=False))
        comp_btn_layout.addWidget(self.comp_btn)
        comp_btn_layout.addWidget(self.comp_folder_btn)

        self.comp_label = QLabel("No comparison video/folder loaded")
        self.comp_label.setFont(QFont("Courier New", 9))
        self.comp_label.setWordWrap(True)

        file_layout.addLayout(comp_btn_layout)
        file_layout.addWidget(self.comp_label, 1)

        main_layout.addLayout(file_layout)

        # --- CONTROLS ROW ---
        controls_layout = QHBoxLayout()

        # Frame slider
        self.frame_slider = QSlider(Qt.Orientation.Horizontal)
        self.frame_slider.setMinimum(0)
        self.frame_slider.setMaximum(0)
        self.frame_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.frame_slider.valueChanged.connect(self.on_frame_changed)
        self.frame_label = QLabel("0 / 0")
        controls_layout.addWidget(QLabel("Frame:"))
        controls_layout.addWidget(self.frame_slider, 1)
        controls_layout.addWidget(self.frame_label)

        # Play button
        self.play_btn = QPushButton("▶ Play")
        self.play_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.play_btn.clicked.connect(self.toggle_play)
        self.play_btn.setMaximumWidth(80)
        controls_layout.addWidget(self.play_btn)

        # Loop button
        self.loop_btn = QPushButton("🔄 Loop: ON")
        self.loop_btn.setCheckable(True)
        self.loop_btn.setChecked(True)
        self.loop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.loop_btn.clicked.connect(self.toggle_loop)
        self.loop_btn.setMaximumWidth(100)
        self.loop_btn.setStyleSheet("background-color: #4CAF50; color: white;")
        controls_layout.addWidget(self.loop_btn)

        # Speed control
        controls_layout.addWidget(QLabel("Speed:"))
        self.speed_spinbox = QDoubleSpinBox()
        self.speed_spinbox.setMinimum(0.1)
        self.speed_spinbox.setMaximum(5.0)
        self.speed_spinbox.setValue(1.0)
        self.speed_spinbox.setSingleStep(0.1)
        self.speed_spinbox.setDecimals(1)
        self.speed_spinbox.setMaximumWidth(70)
        controls_layout.addWidget(self.speed_spinbox)

        # Rotation buttons
        self.rotate_left_btn = QPushButton("↺ -90°")
        self.rotate_left_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rotate_left_btn.clicked.connect(self.rotate_left)
        self.rotate_left_btn.setMaximumWidth(80)
        controls_layout.addWidget(self.rotate_left_btn)

        self.rotate_right_btn = QPushButton("↻ +90°")
        self.rotate_right_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rotate_right_btn.clicked.connect(self.rotate_right)
        self.rotate_right_btn.setMaximumWidth(80)
        controls_layout.addWidget(self.rotate_right_btn)

        self.reset_rotation_btn = QPushButton("Reset Rot")
        self.reset_rotation_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.reset_rotation_btn.clicked.connect(self.reset_rotation)
        self.reset_rotation_btn.setMaximumWidth(80)
        controls_layout.addWidget(self.reset_rotation_btn)

        # Fit to screen button
        self.fit_screen_btn = QPushButton("Fit Screen")
        self.fit_screen_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.fit_screen_btn.clicked.connect(self.fit_to_screen)
        self.fit_screen_btn.setMaximumWidth(100)
        controls_layout.addWidget(self.fit_screen_btn)

        # Swap button
        self.swap_btn = QPushButton("Swap L/R")
        self.swap_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.swap_btn.clicked.connect(self.swap_left_right)
        self.swap_btn.setMaximumWidth(80)
        controls_layout.addWidget(self.swap_btn)

        # Diff toggle button - NOT checkable, just regular button
        self.diff_toggle_btn = QPushButton("Hide Diff")
        self.diff_toggle_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.diff_toggle_btn.clicked.connect(self.toggle_diff_view)
        self.diff_toggle_btn.setMaximumWidth(90)
        controls_layout.addWidget(self.diff_toggle_btn)

        main_layout.addLayout(controls_layout)

        # --- INSTRUCTIONS ---
        instr = QLabel("Mouse wheel: zoom | Drag: pan | +/- keys: zoom | Arrow keys: pan | Space: play/pause")
        main_layout.addWidget(instr)

        # --- IMAGE VIEWERS ---
        img_layout = QHBoxLayout()

        # Left viewer (reference)
        left_layout = QVBoxLayout()
        self.left_title = QLabel("Reference Frame")
        left_layout.addWidget(self.left_title)
        self.left_view = ImageViewer()
        self.left_view.pixel_hovered.connect(self.on_pixel_hovered)
        self.left_view.zoom_requested.connect(self.on_zoom_requested)
        self.left_view.pan_requested.connect(self.on_pan_requested)
        self.left_view.files_dropped.connect(lambda paths: self._load_from_drop(paths, is_reference=True))
        left_layout.addWidget(self.left_view, 1)

        # Middle viewer (comparison)
        mid_layout = QVBoxLayout()
        self.mid_title = QLabel("Comparison Frame (resized)")
        mid_layout.addWidget(self.mid_title)
        self.mid_view = ImageViewer()
        self.mid_view.pixel_hovered.connect(self.on_pixel_hovered)
        self.mid_view.zoom_requested.connect(self.on_zoom_requested)
        self.mid_view.pan_requested.connect(self.on_pan_requested)
        self.mid_view.files_dropped.connect(lambda paths: self._load_from_drop(paths, is_reference=False))
        mid_layout.addWidget(self.mid_view, 1)

        # Right viewer (difference) - wrap in QWidget to enable hide/show
        right_layout = QVBoxLayout()
        self.right_title = QLabel("Difference (Black=0, Blue=Small, Red=Large)")
        right_layout.addWidget(self.right_title)
        self.right_view = ImageViewer()
        self.right_view.pixel_hovered.connect(self.on_pixel_hovered)
        self.right_view.zoom_requested.connect(self.on_zoom_requested)
        self.right_view.pan_requested.connect(self.on_pan_requested)
        right_layout.addWidget(self.right_view, 1)

        # Wrapper widget for right panel
        self.right_panel_widget = QWidget()
        self.right_panel_widget.setLayout(right_layout)

        self.img_layout = img_layout
        img_layout.addLayout(left_layout, 1)
        img_layout.addLayout(mid_layout, 1)
        img_layout.addWidget(self.right_panel_widget, 1)

        main_layout.addLayout(img_layout, 1)

        # --- PIXEL INFO ---
        self.pixel_info_label = QLabel("Hover over image to inspect pixel values")
        self.pixel_info_label.setStyleSheet(
            "border: 1px solid #ccc; padding: 8px; background: #f5f5f5; font-family: monospace;"
        )
        self.pixel_info_label.setMinimumHeight(70)
        main_layout.addWidget(self.pixel_info_label)

        central.setLayout(main_layout)

    # ========================================================================
    # VIDEO & FOLDER LOADING
    # ========================================================================

    def _show_and_load_source(self, dialog_type: str, is_reference: bool):
        """
        Show file/folder open dialog and load the selected source.

        Args:
            dialog_type: 'video' or 'folder'
            is_reference: True for reference, False for comparison
        """
        if dialog_type == 'video':
            path, _ = QFileDialog.getOpenFileName(
                self,
                f"Open {'Reference' if is_reference else 'Comparison'} Video",
                "",
                "Video Files (*.mp4 *.avi *.mov *.mkv)"
            )
        else:  # folder
            path = QFileDialog.getExistingDirectory(
                self,
                f"Select {'Reference' if is_reference else 'Comparison'} Image Folder"
            )

        if path:
            self._load_source(path, is_reference=is_reference)

    def _load_from_drop(self, file_paths: list, is_reference: bool):
        """Handle dropped files."""
        if file_paths:
            self._load_source(file_paths[0], is_reference=is_reference)

    def _load_source(self, file_path: str, is_reference: bool):
        """
        Universal loader: detects file vs folder and loads appropriately.

        Args:
            file_path: Path to video file or image folder
            is_reference: True for reference, False for comparison
        """
        path_obj = Path(file_path)

        if not path_obj.exists():
            QMessageBox.warning(self, "Error", f"Path does not exist: {file_path}")
            return

        info = None

        if path_obj.is_file():
            # Try to load as video
            ext = path_obj.suffix.lower()
            if ext in ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']:
                info = self.comparator.load_video(file_path)
            else:
                QMessageBox.warning(self, "Error", f"Unsupported file type: {ext}")
                return

        elif path_obj.is_dir():
            # Load as image folder
            info = self.comparator.load_images_from_folder(file_path)

        if info is None:
            QMessageBox.warning(self, "Error", f"Failed to load: {file_path}")
            return

        self._set_source_info(info, file_path, is_reference)

    def _set_source_info(self, info: dict, file_path: str, is_reference: bool):
        """
        Update comparator and UI after successful load.

        Args:
            info: Frame info dict from load_video or load_images_from_folder
            file_path: Source file/folder path
            is_reference: True for reference, False for comparison
        """
        if is_reference:
            self.comparator.set_ref(info)
            self.ref_path = file_path
            self.ref_label.setText(f"Ref: {file_path}")
            logger.info(f"Reference loaded: {file_path}")
        else:
            self.comparator.set_comp(info)
            self.comp_path = file_path
            self.comp_label.setText(f"Comp: {file_path}")
            logger.info(f"Comparison loaded: {file_path}")

        self._reset_state_after_load()

    def _reset_state_after_load(self):
        """Reset zoom, pan, rotation, playback after new source loaded."""
        n = self.comparator.frame_count()
        if n == 0:
            return

        self.frame_slider.setMaximum(n - 1)
        self.frame_slider.setValue(0)
        self.zoom = 1.0
        self.pan_x = 0
        self.pan_y = 0
        self.rotation_angle = 0
        self.is_playing = False
        self.play_btn.setText("▶ Play")
        self.playback_timer.stop()

        logger.info(f"State reset after load. Total frames: {n}")
        self.on_frame_changed(0)

    # ========================================================================
    # DIFF TOGGLE
    # ========================================================================

    def toggle_diff_view(self):
        """Show/hide the difference viewer and skip its computation when hidden."""
        self.diff_visible = not self.diff_visible
        if self.diff_visible:
            self.diff_toggle_btn.setText("Hide Diff")
            self.right_panel_widget.show()
        else:
            self.diff_toggle_btn.setText("Show Diff")
            self.right_panel_widget.hide()
        self.on_frame_changed(self.frame_slider.value())

    # ========================================================================
    # FRAME DISPLAY & TRANSFORMS
    # ========================================================================

    def _apply_view_transform(self, img: np.ndarray, do_print=False) -> np.ndarray:
        """
        Apply rotation, zoom, and pan transformations to image.

        Process:
        1. Rotate image if needed (changes effective dimensions)
        2. return the desired crop

        Important: Returns raw crop (not resized) to maximize pixel usage. Qt's pixmap
        scaling in _set_pixmap handles fitting to the label widget.
        """
        # 1) Apply rotation (changes image w,h)
        if self.rotation_angle == 90:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif self.rotation_angle == 180:
            img = cv2.rotate(img, cv2.ROTATE_180)
        elif self.rotation_angle == 270:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        return self._zoom_in1(img, do_print=do_print)

    # -> ndarray[tuple[int, ...], dtype[_SCT]]:
    def _zoom_in1(self, img: Mat | ndarray[Any, dtype[integer[Any] | floating[Any]]] | ndarray, do_print=False) -> ndarray:
        out_h, out_w = self.left_view.height(), self.left_view.width()
        crop_h, crop_w = int(out_h // self.zoom // 2) * 2, int(out_w // self.zoom // 2) * 2
        target_shape = (crop_h, crop_w, 3)

        # Check if we need to reallocate
        if self._zoom_buffer_shape != target_shape:
            self._zoom_buffer = np.zeros(target_shape, dtype=img.dtype)
            self._zoom_buffer_shape = target_shape
        else:
            # Reuse existing buffer, just clear it
            self._zoom_buffer[:] = 0

        out_img = self._zoom_buffer

        h, w = img.shape[:2]
        img_h_c, img_w_c = h // 2, w // 2

        # Pan the center
        clamped_h = int(np.clip(self.pan_y, min=-img_h_c+crop_h//2, max=img_h_c-crop_h//2))
        clamped_w = int(np.clip(self.pan_x, min=-img_w_c+crop_w//2, max=img_w_c-crop_w//2))
        self.pan_x = clamped_w
        self.pan_y = clamped_h
        img_h_c, img_w_c = img_h_c + clamped_h, img_w_c + clamped_w

        # crop and paste
        crop_h_start, crop_w_start = max(0, img_h_c - crop_h // 2), max(0, img_w_c - crop_w // 2)
        crop_h_end, crop_w_end = img_h_c + crop_h // 2, img_w_c + crop_w // 2
        crop_h_actual, crop_w_actual = crop_h_end - crop_h_start, crop_w_end - crop_w_start

        crop = img[crop_h_start:crop_h_end, crop_w_start:crop_w_end]
        out_img[crop_h // 2 - crop_h_actual // 2:crop_h // 2 + crop_h_actual // 2,
        crop_w // 2 - crop_w_actual // 2:crop_w // 2 + crop_w_actual // 2] = crop

        out_img = cv2.resize(out_img, (out_w, out_h), interpolation=cv2.INTER_NEAREST)
        if do_print:
            logger.debug(
                f"Transform (x,y): rot={self.rotation_angle}°, zoom={self.zoom:.2f}, "
                f"img={w}x{h}, crop={crop_w_actual}x{crop_h_actual}, output={out_w}x{out_h}, "
                f"pan=({self.pan_x},{self.pan_y}))"
            )
        # CRITICAL: Ensure contiguous memory layout for QImage conversion
        return np.ascontiguousarray(out_img)

    def on_frame_changed(self, idx: int):
        """Handle frame change: load and display new frame."""
        compute_diff = self.diff_visible
        ref, comp, diff = self.comparator.get_frame_triplet(idx, compute_diff=compute_diff)
        if ref is None:
            return
        self._display_triplet(ref, comp, diff)
        total = self.comparator.frame_count()
        self.frame_label.setText(f"{idx} / {total - 1}")
        self.pixel_info_label.setText("Hover over image to inspect pixel values")

    def _display_triplet(self, ref, comp, diff):
        """Apply transforms and display all three frames."""
        ref_t = self._apply_view_transform(ref, do_print=True)
        comp_t = self._apply_view_transform(comp)

        self._set_pixmap(self.left_view, ref_t)
        self._set_pixmap(self.mid_view, comp_t)
        if diff is not None and self.diff_visible:
            diff_t = self._apply_view_transform(diff)
            self._set_pixmap(self.right_view, diff_t)

    def _set_pixmap(self, label: QLabel, img_np: np.ndarray):
        """Convert numpy image to QPixmap and set on label with aspect-aware scaling."""
        # scale_mode = Qt.TransformationMode.SmoothTransformation
        scale_mode = Qt.TransformationMode.FastTransformation
        h, w = img_np.shape[:2]
        qimg = QImage(img_np.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pm = QPixmap.fromImage(qimg)

        label_w = label.width()
        label_h = label.height()

        if label_w > 0 and label_h > 0:
            # Only scale DOWN if image is larger than label
            if pm.width() > label_w or pm.height() > label_h:
                # Use aspect-ratio-aware scaling to avoid distortion
                if pm.width() / label_w > pm.height() / label_h:
                    pm = pm.scaledToWidth(label_w, scale_mode)
                else:
                    pm = pm.scaledToHeight(label_h, scale_mode)

        label.setPixmap(pm)

    # ========================================================================
    # ZOOM & PAN
    # ========================================================================

    def on_zoom_requested(self, delta: float):
        """Handle zoom request (from mouse wheel or keyboard)."""
        if delta > 0:
            delta = self.zoom_delta
        else:
            delta = -self.zoom_delta
        old_zoom = self.zoom
        self.zoom = max(0.1, min(8.0, self.zoom + delta))
        logger.debug(f"Zoom: {old_zoom:.2f} → {self.zoom:.2f}")
        self.on_frame_changed(self.frame_slider.value())

    def on_pan_requested(self, dx: int, dy: int):
        """Handle pan request (from mouse drag or keyboard)."""
        self.pan_x += dx
        self.pan_y += dy
        logger.debug(f"Pan request: dx={dx}, dy={dy} → pan_x={self.pan_x}, pan_y={self.pan_y}")
        self.on_frame_changed(self.frame_slider.value())

    def keyPressEvent(self, event):
        """Handle keyboard shortcuts."""
        key = event.key()
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.on_zoom_requested(self.zoom_delta)
            event.accept()
        elif key == Qt.Key.Key_Minus:
            self.on_zoom_requested(-self.zoom_delta)
            event.accept()
        elif key == Qt.Key.Key_Left:
            self.on_pan_requested(-20, 0)
            event.accept()
        elif key == Qt.Key.Key_Right:
            self.on_pan_requested(+20, 0)
            event.accept()
        elif key == Qt.Key.Key_Up:
            self.on_pan_requested(0, -20)
            event.accept()
        elif key == Qt.Key.Key_Down:
            self.on_pan_requested(0, +20)
            event.accept()
        else:
            super().keyPressEvent(event)

    # ========================================================================
    # ROTATION
    # ========================================================================

    def _reset_pan_and_refresh(self):
        """Reset pan to (0,0) and refresh display."""
        self.pan_x = 0
        self.pan_y = 0
        self.on_frame_changed(self.frame_slider.value())

    def rotate_left(self):
        """Rotate images -90 degrees."""
        self.rotation_angle = (self.rotation_angle - 90) % 360
        logger.info(f"Rotated left, angle now: {self.rotation_angle}")
        self._reset_pan_and_refresh()

    def rotate_right(self):
        """Rotate images +90 degrees."""
        self.rotation_angle = (self.rotation_angle + 90) % 360
        logger.info(f"Rotated right, angle now: {self.rotation_angle}")
        self._reset_pan_and_refresh()

    def reset_rotation(self):
        """Reset rotation to 0 degrees."""
        self.rotation_angle = 0
        logger.info("Rotation reset to 0")
        self._reset_pan_and_refresh()

    # ========================================================================
    # FIT TO SCREEN
    # ========================================================================

    def fit_to_screen(self):
        """Reset zoom to fit image in label and pan to (0, 0) for full image view."""
        if not self.comparator.ref_info:
            return
        out_h, out_w = self.left_view.height(), self.left_view.width()
        if self.rotation_angle in [90, 270]:
            out_h, out_w = out_w, out_h

        self.zoom = min(out_w / self.comparator.ref_info['width'],
                        out_h / self.comparator.ref_info['height'])

        self.pan_x = 0
        self.pan_y = 0
        logger.info(f"Fit to screen: zoom={self.zoom}")
        self.on_frame_changed(self.frame_slider.value())

    # ========================================================================
    # PIXEL INFO (HOVER-BASED)
    # ========================================================================

    def on_pixel_hovered(self, x: int, y: int):
        """Display RGB values at hovered pixel (real-time)."""
        info = self.comparator.get_pixel_info(x, y)
        if not info:
            return
        r1, g1, b1 = info["img1"]
        r2, g2, b2 = info["img2"]
        txt = (
            f"Pos: (x={info['x']}, y={info['y']}) "
            f"Frame: {self.comparator.current_frame_idx}\n"
            f"Image1 RGB: ({r1}, {g1}, {b1})\n"
            f"Image2 RGB: ({r2}, {g2}, {b2})"
        )
        self.pixel_info_label.setText(txt)

    # ========================================================================
    # PLAYBACK
    # ========================================================================

    def toggle_play(self):
        """Start/stop video playback."""
        if not self.comparator.frame_count():
            QMessageBox.warning(self, "Error", "No videos/folders loaded")
            return

        if self.is_playing:
            self.playback_timer.stop()
            self.is_playing = False
            self.play_btn.setText("▶ Play")
            logger.info("Playback stopped")
        else:
            self.is_playing = True
            self.play_btn.setText("⏸ Pause")
            self.update_playback_timer()
            self.playback_timer.start()
            logger.info("Playback started")

    def toggle_loop(self):
        """Toggle looping on/off."""
        self.loop_enabled = self.loop_btn.isChecked()
        if self.loop_enabled:
            self.loop_btn.setText("🔄 Loop: ON")
            self.loop_btn.setStyleSheet("background-color: #4CAF50; color: white;")
            logger.info("Loop enabled")
        else:
            self.loop_btn.setText("🔄 Loop: OFF")
            self.loop_btn.setStyleSheet("background-color: #f44336; color: white;")
            logger.info("Loop disabled")

    def update_playback_timer(self):
        """Update timer interval based on playback speed."""
        speed = self.speed_spinbox.value()
        interval = int(33 / speed)  # Base interval: 33ms (30fps)
        interval = max(2, interval)  # At least 2ms for responsiveness
        self.playback_timer.setInterval(interval)

        # Prevent timer coalescing - ensure every timeout fires
        self.playback_timer.setTimerType(Qt.TimerType.PreciseTimer)

    def advance_frame(self):
        """Advance to next frame during playback."""
        start = time.perf_counter()
        current = self.frame_slider.value()
        total = self.comparator.frame_count()
        next_frame = current + 1

        if next_frame >= total:
            if self.loop_enabled:
                next_frame = 0
            else:
                self.is_playing = False
                self.play_btn.setText("▶ Play")
                self.playback_timer.stop()
                logger.info("Playback finished (no loop)")
                return

        self.frame_slider.setValue(next_frame)

        elapsed = time.perf_counter() - start
        logger.debug(f"advance_frame took: {elapsed * 1000:.1f} ms")

    # ========================================================================
    # SWAP LEFT/RIGHT
    # ========================================================================

    def swap_left_right(self):
        """Swap reference and comparison videos/folders."""
        self.comparator.ref_frames, self.comparator.comp_frames = \
            self.comparator.comp_frames, self.comparator.ref_frames
        self.comparator.ref_info, self.comparator.comp_info = \
            self.comparator.comp_info, self.comparator.ref_info
        self.ref_path, self.comp_path = self.comp_path, self.ref_path
        self.ref_label.setText(f"Ref: {self.ref_path or 'None'}")
        self.comp_label.setText(f"Comp: {self.comp_path or 'None'}")

        left_title_text = self.left_title.text()
        self.left_title.setText(self.mid_title.text())
        self.mid_title.setText(left_title_text)

        logger.info("Swapped left/right videos/folders")

        if self.comparator.frame_count() > 0:
            self.on_frame_changed(self.frame_slider.value())


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    setup_logging()
    logger = logging.getLogger(__name__)
    # rest of your app

    app = QApplication(sys.argv)
    app.setApplicationName("Video Comparator")
    app.setApplicationVersion("1.0")

    logger.info("=== Application starting ===")

    win = VideoComparatorApp()

    # Set app-level icon for taskbar
    # icon_path = Path(__file__).parent / "app_icon_ms.ico"
    icon_path = "app_icon_ms.ico"
    qicon = QIcon(str(icon_path))
    if qicon.isNull():
        logger.info("ERROR: Icon not found or invalid!")
    else:
        logger.info("Icon loaded successfully")
        win.setWindowIcon(qicon)
    # win.setWindowIcon(QIcon("C:\\Users\\danr\\PycharmProjects\\video_comp_imgui\\app_icon_ms.ico"))

    win.show()
    sys.exit(app.exec())
