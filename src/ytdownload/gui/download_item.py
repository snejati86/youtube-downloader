"""
Widget for displaying download progress items in a list.

This module defines a widget to display download progress in the UI.
"""
from typing import Callable, Optional

from PyQt6.QtCore import Qt, QSize, QMetaObject, pyqtSlot, Q_ARG, QObject, QThread
from PyQt6.QtGui import QIcon, QFont
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QPushButton,
    QProgressBar, QSizePolicy, QApplication
)

from ytdownload.services.downloader import DownloadProgress
from ytdownload.utils.logger import get_logger

# Get logger
logger = get_logger()


class DownloadItemWidget(QWidget):
    """Widget for displaying a download item in a list."""
    
    def __init__(
        self, 
        progress: DownloadProgress, 
        cancel_callback: Callable[[str], None],
        parent: Optional[QWidget] = None
    ):
        """
        Initialize the download item widget.

        Args:
            progress: Download progress information
            cancel_callback: Callback function when download is canceled
            parent: Parent widget
        """
        super().__init__(parent)
        
        self.video_id = progress.video_id
        self.title = progress.title
        self.cancel_callback = cancel_callback
        
        # Status tracking properties
        self.is_completed = False
        self.is_canceled = False
        self.has_error = False
        
        self.init_ui()
        self.update_progress(progress)
        
    def init_ui(self):
        """Set up the user interface components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)
        
        # Top row with title and cancel button
        top_layout = QHBoxLayout()
        top_layout.setSpacing(10)
        
        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setFont(QFont("", 12, QFont.Weight.Bold))
        self.title_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        top_layout.addWidget(self.title_label)
        
        # Cancel button
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setFixedWidth(80)
        self.cancel_button.setStyleSheet("""
            QPushButton {
                background-color: #ff3b30;
                color: white;
                border-radius: 4px;
                padding: 4px 8px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff453a;
            }
            QPushButton:pressed {
                background-color: #d70015;
            }
            QPushButton:disabled {
                background-color: #a1a1a6;
            }
        """)
        self.cancel_button.clicked.connect(self.cancel_download)
        top_layout.addWidget(self.cancel_button)
        
        layout.addLayout(top_layout)
        
        # Middle row with progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p% - %v")
        layout.addWidget(self.progress_bar)
        
        # Bottom row with status
        self.status_label = QLabel("Waiting...")
        self.status_label.setStyleSheet("color: #666;")
        layout.addWidget(self.status_label)
        
        # Set fixed height for consistent sizing
        self.setFixedHeight(100)
        
        # Add a bottom border
        self.setStyleSheet("""
            DownloadItemWidget {
                border-bottom: 1px solid #e0e0e0;
                background-color: white;
                border-radius: 6px;
            }
        """)

    def update_progress(self, progress: DownloadProgress):
        """
        Update the widget with progress information.
        
        Args:
            progress: Download progress information
        """
        # Use invokeMethod to ensure UI updates happen on the main thread
        # This avoids threading issues with Qt painters
        QMetaObject.invokeMethod(
            self, 
            "_update_progress_safe", 
            Qt.ConnectionType.QueuedConnection,
            Q_ARG(object, progress)
        )
    
    @pyqtSlot(object)
    def _update_progress_safe(self, progress: DownloadProgress):
        """
        Thread-safe method to update the UI with progress information.
        Called via QMetaObject.invokeMethod to ensure it runs on the main thread.
        
        Args:
            progress: Download progress information
        """
        try:
            # Store the progress info
            self.progress = progress
            
            # Ensure we're on the main thread
            if QThread.currentThread() != QApplication.instance().thread():
                logger.warning("Attempted UI update from non-main thread, forcing thread-safe call")
                QMetaObject.invokeMethod(
                    self, 
                    "_update_progress_safe", 
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(object, progress)
                )
                return
                
            # Update progress bar
            if progress.error:
                # Show error state
                self.progress_bar.setValue(0)
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #d1d1d6;
                        border-radius: 5px;
                        background-color: #f0f0f0;
                        text-align: center;
                    }
                    QProgressBar::chunk {
                        background-color: #ff3b30;
                        border-radius: 5px;
                    }
                """)
                self.status_label.setText(f"Error: {progress.error}")
                self.status_label.setStyleSheet("color: #ff3b30; font-weight: bold;")
                logger.error(f"Download error for {progress.title}: {progress.error}")
                self.has_error = True
                
            elif progress.is_complete:
                # Show complete state
                self.progress_bar.setValue(100)
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #d1d1d6;
                        border-radius: 5px;
                        background-color: #f0f0f0;
                        text-align: center;
                    }
                    QProgressBar::chunk {
                        background-color: #34c759;
                        border-radius: 5px;
                    }
                """)
                self.status_label.setText("Complete")
                self.status_label.setStyleSheet("color: #34c759; font-weight: bold;")
                logger.info(f"Download completed for {progress.title}")
                self.is_completed = True
                
            elif progress.status == "Canceled":
                # Show canceled state
                self.progress_bar.setValue(0)
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #d1d1d6;
                        border-radius: 5px;
                        background-color: #f0f0f0;
                        text-align: center;
                    }
                    QProgressBar::chunk {
                        background-color: #ff9500;
                        border-radius: 5px;
                    }
                """)
                self.status_label.setText("Canceled")
                self.status_label.setStyleSheet("color: #ff9500; font-weight: bold;")
                logger.info(f"Download canceled for {progress.title}")
                self.is_canceled = True
                
            else:
                # Update normal progress
                self.progress_bar.setValue(int(progress.progress))
                
                # Default style
                self.progress_bar.setStyleSheet("""
                    QProgressBar {
                        border: 1px solid #d1d1d6;
                        border-radius: 5px;
                        background-color: #f0f0f0;
                        text-align: center;
                    }
                    QProgressBar::chunk {
                        background-color: #007aff;
                        border-radius: 5px;
                    }
                """)
                
                # Detect transcript downloads and provide more informative status
                if "transcript" in progress.status.lower() or "subtitle" in progress.status.lower():
                    # For transcript downloads, provide more detailed information
                    self.status_label.setText(progress.status)
                    self.status_label.setStyleSheet("color: #007aff;")
                    
                    # Make progress bar pulsate for long transcript operations
                    if "verifying" in progress.status.lower() or "processing" in progress.status.lower():
                        self.progress_bar.setFormat("%p% - " + progress.status)
                else:
                    # Regular download progress
                    self.status_label.setText(progress.status)
                    self.status_label.setStyleSheet("color: #666;")
                
            # Show/hide cancel button based on state
            self.cancel_button.setVisible(not progress.is_complete and progress.status != "Canceled" and not progress.error)
        except Exception as e:
            logger.error(f"Error updating download UI: {str(e)}", exc_info=True)

    def cancel_download(self):
        """Cancel the download."""
        self.cancel_button.setEnabled(False)
        self.status_label.setText("Canceling...")
        logger.info(f"Canceling download for {self.title}")
        self.cancel_callback(self.video_id)
        
    def sizeHint(self) -> QSize:
        """
        Get the preferred size of the widget.

        Returns:
            QSize: Preferred size
        """
        return QSize(0, 100) 