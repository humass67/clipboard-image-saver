import os
import sys
import datetime
import logging
from logging.handlers import RotatingFileHandler

from PyQt5.QtCore import Qt, QCoreApplication, QMimeData, QUrl, QTimer, QEvent
from PyQt5.QtGui import QIcon, QPixmap, QImage, QPainter, QColor, QFont, QCursor
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QShortcut, QSystemTrayIcon, QMenu, QAction, QStyle,
    QFrame, QGraphicsDropShadowEffect, QSizePolicy,
)

if getattr(sys, 'frozen', False):
    BASE = os.path.dirname(sys.executable)
else:
    BASE = os.path.dirname(os.path.abspath(__file__))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[RotatingFileHandler(os.path.join(BASE, 'clipboard_saver.log'), maxBytes=1_048_576, backupCount=3, encoding='utf-8'), logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------
# TitleBar
# ---------------------------------------------------------------
class TitleBar(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setFixedHeight(38)
        self._drag_pos = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)

        layout.addStretch()

        self.min_btn = self._make_btn("─")
        self.max_btn = self._make_btn("□")
        self.close_btn = self._make_btn("✕")
        self.close_btn.setObjectName("titleClose")

        self.min_btn.clicked.connect(self.window().showMinimized)
        self.max_btn.clicked.connect(self._toggle_max)
        self.close_btn.clicked.connect(self.window().close)

        layout.addWidget(self.min_btn)
        layout.addWidget(self.max_btn)
        layout.addWidget(self.close_btn)

    def _make_btn(self, text):
        b = QPushButton(text)
        b.setFixedSize(38, 28)
        b.setFlat(True)
        b.setCursor(QCursor(Qt.ArrowCursor))
        return b

    def _toggle_max(self):
        w = self.window()
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor("#89b4fa"))
        p.setFont(QFont("Segoe UI", 12))
        p.drawText(14, 26, "●")
        p.setPen(QColor("#cdd6f4"))
        f = QFont("Segoe UI", 11)
        f.setBold(True)
        p.setFont(f)
        p.drawText(36, 26, "Clipboard Image Saver")

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton and self._drag_pos is not None:
            delta = event.globalPos() - self._drag_pos
            w = self.window()
            w.move(w.x() + delta.x(), w.y() + delta.y())
            self._drag_pos = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = None

    def mouseDoubleClickEvent(self, event):
        self._toggle_max()


# ---------------------------------------------------------------
# ClipboardSaver
# ---------------------------------------------------------------
class ClipboardSaver(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setMinimumSize(480, 480)
        self.resize(540, 540)

        self.save_dir = os.path.join(BASE, "screenshots")
        os.makedirs(self.save_dir, exist_ok=True)

        self.last_saved_path = None
        self.clipboard = QApplication.clipboard()
        self.clipboard.dataChanged.connect(self.refresh_preview)
        self._own_clipboard = False
        self._last_set_url = None
        self._deferred_active = False
        self._resize_margin = 6

        self._build_ui()
        self._build_tray()
        self._apply_theme()

        QShortcut(Qt.CTRL + Qt.Key_V, self).activated.connect(self.handle_paste)
        QShortcut(Qt.CTRL + Qt.Key_C, self).activated.connect(self.handle_copy)

    # ======================== UI ========================

    def _build_ui(self):
        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(20, 20, 20, 20)

        self.container = QFrame()
        self.container.setObjectName("appContainer")

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.container.setGraphicsEffect(shadow)

        inner = QVBoxLayout(self.container)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.setSpacing(0)

        # Title bar
        self.title_bar = TitleBar(self)
        inner.addWidget(self.title_bar)

        # Content
        content = QVBoxLayout()
        content.setContentsMargins(28, 16, 28, 22)
        content.setSpacing(10)

        # Preview
        self.image_label = QLabel()
        self.image_label.setObjectName("preview")
        self.image_label.setMinimumSize(400, 260)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.image_label.setText("No image in clipboard")
        self.image_label.setCursor(QCursor(Qt.ArrowCursor))
        content.addWidget(self.image_label, stretch=1)

        # File info
        self.info_label = QLabel()
        self.info_label.setObjectName("fileInfo")
        self.info_label.setAlignment(Qt.AlignCenter)
        content.addWidget(self.info_label)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self.paste_btn = QPushButton("Paste (Ctrl+V)")
        self.copy_btn = QPushButton("Copy (Ctrl+C)")
        self.paste_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.copy_btn.setCursor(QCursor(Qt.PointingHandCursor))
        self.paste_btn.clicked.connect(self.handle_paste)
        self.copy_btn.clicked.connect(self.handle_copy)
        btn_row.addStretch()
        btn_row.addWidget(self.paste_btn)
        btn_row.addWidget(self.copy_btn)
        btn_row.addStretch()
        content.addLayout(btn_row)

        # Status bar
        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 4, 0, 0)
        self.status_label = QLabel("●  Monitoring clipboard")
        self.status_label.setObjectName("statusText")
        self.folder_label = QLabel("📂 screenshots/")
        self.folder_label.setObjectName("folderText")
        status_row.addWidget(self.status_label)
        status_row.addStretch()
        status_row.addWidget(self.folder_label)
        content.addLayout(status_row)

        inner.addLayout(content)
        self._main_layout.addWidget(self.container)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(self)
        icon = self.style().standardIcon(QStyle.SP_ComputerIcon)
        self.tray.setIcon(icon)
        self.tray.setToolTip("Clipboard Image Saver")
        tray_menu = QMenu()
        show_a = QAction("Show", self)
        quit_a = QAction("Quit", self)
        show_a.triggered.connect(self.show_window)
        quit_a.triggered.connect(QCoreApplication.quit)
        tray_menu.addAction(show_a)
        tray_menu.addAction(quit_a)
        self.tray.setContextMenu(tray_menu)
        self.tray.activated.connect(self._on_tray)
        self.tray.show()

    def _apply_theme(self):
        self.setStyleSheet("""
            QWidget { font-family: "Segoe UI"; font-size: 12px; color: #cdd6f4; }
            QFrame#appContainer {
                background: #1e1e2e;
                border-radius: 12px;
            }
            QLabel#preview {
                background-color: #2b2b3d;
                border: 2px solid #45475a;
                border-radius: 10px;
                padding: 4px;
                color: #6c7086;
                font-size: 13px;
            }
            QLabel#fileInfo {
                color: #a6adc8;
                font-size: 11px;
                padding: 2px 0;
            }
            QLabel#statusText {
                color: #a6adc8;
                font-size: 11px;
            }
            QLabel#folderText {
                color: #585b70;
                font-size: 11px;
            }
            QPushButton {
                background: #89b4fa;
                color: #1e1e2e;
                border: none;
                border-radius: 8px;
                padding: 9px 22px;
                font-weight: bold;
                font-size: 12px;
            }
            QPushButton:hover {
                background: #74c7ec;
            }
            QPushButton:pressed {
                background: #89dceb;
            }
            QPushButton:flat {
                background: transparent;
                color: #cdd6f4;
                border-radius: 6px;
                padding: 0;
                font-weight: normal;
                font-size: 14px;
            }
            QPushButton:flat:hover {
                background: #313244;
            }
            QPushButton#titleClose:flat:hover {
                background: #f38ba8;
                color: #1e1e2e;
            }
            QSystemTrayIcon { color: #cdd6f4; }
        """)

    # ======================== Window ========================

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            maximized = self.windowState() & Qt.WindowMaximized
            self.title_bar.max_btn.setText("❐" if maximized else "□")
            self._main_layout.setContentsMargins(0, 0, 0, 0 if maximized else 20)
            if maximized:
                self.container.setGraphicsEffect(None)
                self.container.setStyleSheet("""
                    QFrame#appContainer {
                        background: #1e1e2e;
                        border-radius: 0px;
                    }
                """)
            else:
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(30)
                shadow.setOffset(0, 0)
                shadow.setColor(QColor(0, 0, 0, 120))
                self.container.setGraphicsEffect(shadow)
                self.container.setStyleSheet("""
                    QFrame#appContainer {
                        background: #1e1e2e;
                        border-radius: 12px;
                    }
                """)
            self._apply_theme()
        super().changeEvent(event)

    def mouseMoveEvent(self, event):
        if not self.isMaximized():
            pos = event.pos()
            m = self._resize_margin
            r = self.rect()
            left = pos.x() <= m
            right = pos.x() >= r.width() - m
            top = pos.y() <= m
            bottom = pos.y() >= r.height() - m
            if top and left:
                self.setCursor(QCursor(Qt.SizeFDiagCursor))
            elif top and right:
                self.setCursor(QCursor(Qt.SizeBDiagCursor))
            elif bottom and left:
                self.setCursor(QCursor(Qt.SizeBDiagCursor))
            elif bottom and right:
                self.setCursor(QCursor(Qt.SizeFDiagCursor))
            elif left or right:
                self.setCursor(QCursor(Qt.SizeHorCursor))
            elif top or bottom:
                self.setCursor(QCursor(Qt.SizeVerCursor))
            else:
                self.setCursor(QCursor(Qt.ArrowCursor))

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and not self.isMaximized():
            pos = event.pos()
            m = self._resize_margin
            r = self.rect()
            edge = None
            if pos.x() <= m and pos.y() <= m:
                edge = Qt.TopLeftCorner
            elif pos.x() >= r.width() - m and pos.y() <= m:
                edge = Qt.TopRightCorner
            elif pos.x() <= m and pos.y() >= r.height() - m:
                edge = Qt.BottomLeftCorner
            elif pos.x() >= r.width() - m and pos.y() >= r.height() - m:
                edge = Qt.BottomRightCorner
            elif pos.x() <= m:
                edge = Qt.LeftEdge
            elif pos.x() >= r.width() - m:
                edge = Qt.RightEdge
            elif pos.y() <= m:
                edge = Qt.TopEdge
            elif pos.y() >= r.height() - m:
                edge = Qt.BottomEdge
            if edge and self.windowHandle():
                self.windowHandle().startSystemResize(edge)

    # ======================== Logic ========================

    def _update_file_info(self, qimage=None, path=None):
        parts = []
        if path:
            parts.append(os.path.basename(path))
        if qimage and not qimage.isNull():
            w, h = qimage.width(), qimage.height()
            parts.append(f"{w}\u00d7{h}")
        if path and os.path.exists(path):
            size = os.path.getsize(path)
            if size < 1024:
                parts.append(f"{size} B")
            elif size < 1024 * 1024:
                parts.append(f"{size/1024:.1f} KB")
            else:
                parts.append(f"{size/(1024*1024):.1f} MB")
        self.info_label.setText("    ".join(parts) if parts else "")

    def show_image(self, qimage):
        pix = QPixmap.fromImage(qimage)
        scaled = pix.scaled(
            self.image_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setText("")
        self._update_file_info(qimage=qimage, path=self.last_saved_path)

    def handle_paste(self):
        logger.info("Manual paste triggered")
        if self.clipboard.mimeData().hasImage():
            image = self.clipboard.image()
            if image.isNull():
                self.status_label.setText("●  Failed to read image")
                logger.error("Manual paste: image is null")
                return
            if self.last_saved_path and os.path.exists(self.last_saved_path):
                os.remove(self.last_saved_path)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fn = f"{ts}.png"
            path = os.path.join(self.save_dir, fn)
            if image.save(path, "PNG"):
                self.last_saved_path = path
                self.show_image(image)
                self.status_label.setText("✅  Saved manually")
                logger.info(f"Manual paste: image saved to {path}")
            else:
                self.status_label.setText("●  Error saving file")
                logger.error(f"Manual paste: failed to save image to {path}")
        else:
            self.status_label.setText("●  No image in clipboard")
            logger.info("Manual paste: no image in clipboard")

    def refresh_preview(self):
        try:
            if self._own_clipboard:
                self._own_clipboard = False
                logger.info("Ignoring own clipboard event")
                return
            logger.info("Starting refresh")
            mime = self.clipboard.mimeData()
            logger.info(f"Mime formats: {mime.formats()}, hasImage: {mime.hasImage()}, hasUrls: {mime.hasUrls()}, hasText: {mime.hasText()}")
            if mime.hasUrls() and not mime.hasImage() and self._last_set_url:
                urls = mime.urls()
                if len(urls) == 1 and urls[0] == self._last_set_url:
                    logger.info("Ignoring own clipboard event")
                    return
            if mime.hasImage():
                if not self._deferred_active:
                    self._deferred_active = True
                    QTimer.singleShot(500, self._process_clipboard)
            else:
                self.image_label.clear()
                self.image_label.setPixmap(QPixmap())
                self.image_label.setText("No image in clipboard")
                self.info_label.setText("")
                self.status_label.setText("●  Monitoring clipboard")
                logger.info("Clipboard does not contain an image")
        except Exception as e:
            logger.exception(f"Exception in refresh_preview: {e}")
            self.status_label.setText("●  Clipboard error")

    def _process_clipboard(self):
        self._deferred_active = False
        try:
            mime = self.clipboard.mimeData()
            if not mime.hasImage():
                logger.info("Deferred processing: no image in clipboard anymore")
                return
            img_data = mime.imageData()
            logger.info(f"img_data type: {type(img_data)}")
            if isinstance(img_data, QImage):
                qimg = img_data
            elif isinstance(img_data, QPixmap):
                qimg = img_data.toImage()
            else:
                try:
                    qimg = QImage(img_data)
                except Exception as e:
                    self.status_label.setText("●  Failed to read image")
                    logger.error(f"Failed to convert mime image data to QImage: {e}")
                    return
            if qimg.isNull():
                self.status_label.setText("●  Failed to read image")
                logger.error("Failed to read image from clipboard (null QImage)")
                return
            logger.info("Proceeding to save image")
            if self.last_saved_path and os.path.exists(self.last_saved_path):
                os.remove(self.last_saved_path)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            fn = f"{ts}.png"
            path = os.path.join(self.save_dir, fn)
            try:
                success = qimg.save(path, "PNG")
            except Exception as e:
                success = False
                logger.exception(f"Exception while saving image to {path}: {e}")
            if success:
                self.last_saved_path = path
                self.show_image(qimg)
                self.status_label.setText("✅  Screenshot saved")
                logger.info(f"Image saved to {path}, copying file URL to clipboard")
                mime_file = QMimeData()
                url = QUrl.fromLocalFile(path)
                mime_file.setUrls([url])
                self._own_clipboard = True
                self.clipboard.clear()
                self.clipboard.setMimeData(mime_file)
                self._last_set_url = url
            else:
                self.status_label.setText("●  Save error")
                logger.error(f"Failed to save image to {path}")
        except Exception as e:
            logger.exception(f"Exception in _process_clipboard: {e}")
            self.status_label.setText("●  Clipboard error")

    def handle_copy(self):
        if not self.last_saved_path or not os.path.isfile(self.last_saved_path):
            self.status_label.setText("●  No saved file")
            logger.warning("Manual copy: no saved file available")
            return
        mime = QMimeData()
        url = QUrl.fromLocalFile(self.last_saved_path)
        mime.setUrls([url])
        self._own_clipboard = True
        self.clipboard.clear()
        self.clipboard.setMimeData(mime)
        self._last_set_url = url
        self.status_label.setText("📋  Path copied to clipboard")
        logger.info(f"Manual copy: file URL {self.last_saved_path} copied to clipboard")

    def show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage(
            "Clipboard Image Saver",
            "Application minimized to tray.",
            QSystemTrayIcon.Information,
            2000,
        )

    def _on_tray(self, reason):
        if reason == QSystemTrayIcon.DoubleClick:
            self.show_window()


# ---------------------------------------------------------------
if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = ClipboardSaver()
    win.show()
    sys.exit(app.exec_())
