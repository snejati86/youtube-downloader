"""
Widget for displaying YouTube playlist items in a list.

This module defines a widget to display playlist information in the UI.
"""
import os
import urllib.request
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QSize, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QFont, QIcon
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QSizePolicy, QFrame
)

from ytdownload.api.youtube import Playlist
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
        self.temp_file = os.path.join(os.path.expanduser("~"), f".ytdownload_temp_playlist_thumb_{os.getpid()}_{id(self)}.jpg")
        
    def run(self):
        """Download and load the thumbnail image."""
        try:
            if not self.url:
                logger.warning("Empty playlist thumbnail URL provided")
                self.error_occurred.emit("No thumbnail URL available")
                return
                
            logger.debug(f"Downloading playlist thumbnail from: {self.url}")
            
            # Create a unique temporary file name to avoid conflicts
            try:
                opener = urllib.request.build_opener()
                opener.addheaders = [('User-Agent', 'Mozilla/5.0')]
                urllib.request.install_opener(opener)
                urllib.request.urlretrieve(self.url, self.temp_file)
                
                # Check if the file was actually created and has content
                if not os.path.exists(self.temp_file) or os.path.getsize(self.temp_file) == 0:
                    logger.warning(f"Downloaded playlist thumbnail file is empty or was not created: {self.temp_file}")
                    self.error_occurred.emit("Downloaded thumbnail is empty")
                    return
                    
                logger.debug(f"Successfully downloaded playlist thumbnail to: {self.temp_file}")
                
                pixmap = QPixmap(self.temp_file)
                if pixmap.isNull():
                    logger.warning("Playlist thumbnail image could not be loaded as pixmap")
                    self.error_occurred.emit("Could not create image from downloaded thumbnail")
                    return
                    
                # Scale the image with correct aspect ratio
                pixmap = pixmap.scaled(120, 68, Qt.AspectRatioMode.KeepAspectRatioByExpanding, 
                                      Qt.TransformationMode.SmoothTransformation)
                logger.debug(f"Playlist thumbnail loaded successfully, size: {pixmap.width()}x{pixmap.height()}")
                self.thumbnail_loaded.emit(pixmap)
                
            except Exception as e:
                logger.error(f"Error downloading playlist thumbnail: {str(e)}", exc_info=True)
                self.error_occurred.emit(f"Error loading thumbnail: {str(e)}")
        finally:
            # Always clean up temp file
            try:
                if os.path.exists(self.temp_file):
                    os.remove(self.temp_file)
                    logger.debug(f"Removed temporary playlist thumbnail file: {self.temp_file}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to remove temporary playlist thumbnail file: {str(cleanup_error)}")


class PlaylistItemWidget(QWidget):
    """Widget for displaying a YouTube playlist item in a list."""
    
    def __init__(
        self, 
        playlist: Playlist, 
        on_view_callback: Callable[[str], None],
        parent: Optional[QWidget] = None
    ):
        """
        Initialize the playlist item widget.

        Args:
            playlist: Playlist object containing playlist information
            on_view_callback: Callback function when the View button is clicked
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.playlist = playlist
        self.on_view_callback = on_view_callback
        
        self.init_ui()
        self.load_thumbnail()
        
    def init_ui(self):
        """Set up the user interface components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(15)
        
        # Playlist icon/thumbnail
        self.thumbnail_label = QLabel()
        self.thumbnail_label.setFixedSize(120, 68)  # 16:9 aspect ratio
        self.thumbnail_label.setStyleSheet("""
            background-color: #e0e0e0;
            border-radius: 4px;
        """)
        self.thumbnail_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add playlist symbol/overlay
        icon_layout = QVBoxLayout(self.thumbnail_label)
        icon_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.playlist_symbol = QLabel("▶")  # Play symbol
        self.playlist_symbol.setStyleSheet("""
            font-size: 24px;
            color: #333;
        """)
        icon_layout.addWidget(self.playlist_symbol)
        
        layout.addWidget(self.thumbnail_label)
        
        # Playlist information
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        
        # Title
        title = QLabel(self.playlist.title)
        title.setFont(QFont("", 12, QFont.Weight.Bold))
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        info_layout.addWidget(title)
        
        # Channel
        channel = QLabel(self.playlist.channel_title)
        channel.setStyleSheet("color: #666;")
        info_layout.addWidget(channel)
        
        # Video count
        videos_count = QLabel(f"{self.playlist.video_count} videos")
        videos_count.setStyleSheet("color: #666; font-size: 12px;")
        info_layout.addWidget(videos_count)
        
        layout.addLayout(info_layout)
        
        # View button
        view_button = QPushButton("View Playlist")
        view_button.setFixedWidth(120)
        view_button.setStyleSheet("""
            QPushButton {
                background-color: #0071e3;
                color: white;
                border-radius: 4px;
                padding: 6px 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0077ed;
            }
            QPushButton:pressed {
                background-color: #005bbf;
            }
        """)
        view_button.clicked.connect(self.view_playlist)
        layout.addWidget(view_button)
        
        # Set fixed height for consistent sizing
        self.setFixedHeight(100)
        
        # Add a bottom border
        self.setStyleSheet("""
            PlaylistItemWidget {
                border-bottom: 1px solid #e0e0e0;
                background-color: white;
            }
        """)
    
    def load_thumbnail(self):
        """Load the thumbnail image asynchronously."""
        if not self.playlist.thumbnail_url:
            logger.debug(f"No thumbnail URL for playlist: {self.playlist.title}")
            return
            
        logger.debug(f"Starting thumbnail load for playlist: {self.playlist.title}")
            
        # Start a thread to download and load the thumbnail
        self.thumbnail_loader = ThumbnailLoader(self.playlist.thumbnail_url)
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
            # Keep the overlay visible - just update the background
            self.thumbnail_label.setPixmap(pixmap)
            logger.debug(f"Thumbnail set for playlist: {self.playlist.title}")
            
            # Make the play symbol overlay more visible against the actual thumbnail
            self.playlist_symbol.setStyleSheet("""
                font-size: 24px;
                color: white;
                background-color: rgba(0, 0, 0, 0.5);
                border-radius: 12px;
                padding: 4px;
            """)
        else:
            self.handle_thumbnail_error("Received empty pixmap")
            
    def handle_thumbnail_error(self, error_msg: str):
        """
        Handle thumbnail loading errors.
        
        Args:
            error_msg: Error message
        """
        logger.warning(f"Thumbnail error for playlist {self.playlist.title}: {error_msg}")
        # Make the play symbol more visible since we don't have a thumbnail
        self.playlist_symbol.setStyleSheet("""
            font-size: 24px;
            color: #333;
            padding: 4px;
        """)
    
    def view_playlist(self):
        """Handle the view playlist button click."""
        logger.debug(f"Viewing playlist: {self.playlist.title}")
        self.on_view_callback(self.playlist.playlist_id)
        
    def sizeHint(self) -> QSize:
        """
        Get the preferred size of the widget.

        Returns:
            QSize: Preferred size
        """
        return QSize(0, 100) 