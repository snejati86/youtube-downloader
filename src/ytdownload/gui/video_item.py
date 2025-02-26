"""
Widget for displaying YouTube video items in a list.

This module defines a widget to display video information in the UI.
"""
import os
import urllib.request
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont, QIcon, QImage
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QCheckBox,
    QSizePolicy, QFrame
)

from ytdownload.api.youtube import Video
from ytdownload.utils.helpers import format_duration, format_view_count
from ytdownload.utils.logger import get_logger

# Get logger
logger = get_logger()


class ThumbnailLoader(QThread):
    """Thread for loading thumbnails asynchronously."""
    
    thumbnail_loaded = pyqtSignal(QPixmap)
    error_occurred = pyqtSignal(str)
    
    def __init__(self, url: str):
        """
        Initialize the thumbnail loader.
        
        Args:
            url: URL of the thumbnail image
        """
        super().__init__()
        self.url = url
        self.temp_file = os.path.join(os.path.expanduser("~"), f".ytdownload_temp_thumb_{os.getpid()}_{id(self)}.jpg")
        
    def run(self):
        """Download and load the thumbnail image."""
        try:
            if not self.url:
                logger.warning("Empty thumbnail URL provided")
                self.error_occurred.emit("No thumbnail URL available")
                return
                
            logger.debug(f"Downloading thumbnail from: {self.url}")
            
            # Create a unique temporary file name to avoid conflicts
            try:
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                urllib.request.urlretrieve(self.url, self.temp_file)
                
                # Check if the file was actually created and has content
                if not os.path.exists(self.temp_file) or os.path.getsize(self.temp_file) == 0:
                    logger.warning(f"Downloaded thumbnail file is empty or was not created: {self.temp_file}")
                    self.error_occurred.emit("Downloaded thumbnail is empty")
                    return
                    
                logger.debug(f"Successfully downloaded thumbnail to: {self.temp_file}")
                
                pixmap = QPixmap(self.temp_file)
                if pixmap.isNull():
                    logger.warning("Thumbnail image could not be loaded as pixmap")
                    self.error_occurred.emit("Could not create image from downloaded thumbnail")
                    return
                    
                # Scale the image with correct aspect ratio
                pixmap = pixmap.scaled(120, 68, Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                      Qt.TransformationMode.SmoothTransformation)
                logger.debug(f"Thumbnail loaded successfully, size: {pixmap.width()}x{pixmap.height()}")
                self.thumbnail_loaded.emit(pixmap)
                
            except Exception as e:
                logger.error(f"Error downloading thumbnail: {str(e)}", exc_info=True)
                self.error_occurred.emit(f"Error loading thumbnail: {str(e)}")
        finally:
            # Always clean up temp file
            try:
                if os.path.exists(self.temp_file):
                    os.remove(self.temp_file)
                    logger.debug(f"Removed temporary thumbnail file: {self.temp_file}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove temporary thumbnail file: {str(cleanup_error)}")


class VideoItemWidget(QWidget):
    """Widget for displaying a YouTube video item in a list."""
    
    def __init__(
        self, 
        video: Video, 
        on_select_callback: Callable[[str, bool], None],
        parent: Optional[QWidget] = None
    ):
        """
        Initialize the video item widget.

        Args:
            video: Video object containing video information
            on_select_callback: Callback function when video is selected
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.video = video
        self.on_select_callback = on_select_callback
        
        self.init_ui()
        self.load_thumbnail()
        
    def init_ui(self):
        """Set up the user interface components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Checkbox for selection
        self.checkbox = QCheckBox()
        self.checkbox.setFixedSize(24, 24)
        self.checkbox.stateChanged.connect(self.selection_changed)
        layout.addWidget(self.checkbox)
        
        # Thumbnail placeholder
        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(120, 68)  # 16:9 aspect ratio
        self.thumbnail.setStyleSheet("""
            background-color: #e0e0e0;
            border-radius: 4px;
        """)
        self.thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add a loading indicator text
        self.thumbnail.setText("Loading...")
        
        layout.addWidget(self.thumbnail)
        
        # Video information
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        # Title
        title = QLabel(self.video.title)
        title.setFont(QFont("", 12, QFont.Weight.Bold))
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_layout.addWidget(title)
        
        # Channel
        channel = QLabel(self.video.channel_title)
        channel.setStyleSheet("color: #666;")
        info_layout.addWidget(channel)
        
        # Stats layout (duration, views)
        stats_layout = QHBoxLayout()
        stats_layout.setSpacing(10)
        
        # Duration
        duration_label = QLabel(format_duration(self.video.duration))
        duration_label.setStyleSheet("color: #666; font-size: 12px;")
        stats_layout.addWidget(duration_label)
        
        # Views
        views_label = QLabel(format_view_count(self.video.view_count))
        views_label.setStyleSheet("color: #666; font-size: 12px;")
        stats_layout.addWidget(views_label)
        
        stats_layout.addStretch()
        info_layout.addLayout(stats_layout)
        
        layout.addLayout(info_layout)
        
        # Set fixed height for consistent sizing
        self.setFixedHeight(100)
        
        # Add a bottom border
        self.setStyleSheet("""
            VideoItemWidget {
                border-bottom: 1px solid #e0e0e0;
                background-color: white;
            }
        """)
    
    def load_thumbnail(self):
        """Load the thumbnail image asynchronously."""
        if not self.video.thumbnail_url:
            self.thumbnail.setText("No thumbnail")
            return
        
        logger.debug(f"Starting thumbnail load for video: {self.video.title}")
        self.thumbnail.setText("Loading...")
            
        # Start a thread to download and load the thumbnail
        self.thumbnail_loader = ThumbnailLoader(self.video.thumbnail_url)
        self.thumbnail_loader.thumbnail_loaded.connect(self.set_thumbnail)
        self.thumbnail_loader.error_occurred.connect(self.handle_thumbnail_error)
        self.thumbnail_loader.start()
        
    def set_thumbnail(self, pixmap: QPixmap):
        """
        Set the thumbnail image.
        
        Args:
            pixmap: Pixmap to display
        """
        if not pixmap.isNull():
            self.thumbnail.setText("")  # Clear loading text
            self.thumbnail.setPixmap(pixmap)
            logger.debug(f"Thumbnail set for video: {self.video.title}")
        else:
            self.handle_thumbnail_error("Received empty pixmap")
    
    def handle_thumbnail_error(self, error_msg: str):
        """
        Handle thumbnail loading errors.
        
        Args:
            error_msg: Error message
        """
        logger.warning(f"Thumbnail error for {self.video.title}: {error_msg}")
        self.thumbnail.setText("No thumbnail")
        self.thumbnail.setStyleSheet("""
            background-color: #e0e0e0;
            border-radius: 4px;
            color: #666;
            font-style: italic;
        """)
    
    def selection_changed(self, state: int):
        """
        Handle checkbox state changes.

        Args:
            state: Checkbox state (Qt.CheckState)
        """
        selected = state == Qt.CheckState.Checked.value
        self.on_select_callback(self.video.video_id, selected)
        
    def set_selected(self, selected: bool):
        """
        Programmatically set the selected state.

        Args:
            selected: Whether the item should be selected
        """
        self.checkbox.setChecked(selected)
        
    def sizeHint(self) -> QSize:
        """
        Get the preferred size of the widget.

        Returns:
            QSize: Preferred size
        """
        return QSize(0, 100) 