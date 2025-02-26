"""
Main window for the YouTube Downloader application.

This module defines the main application window and user interface.
"""
import asyncio
import os
import sys
import threading
import time
import queue
from typing import Dict, List, Optional, Set, Tuple, Any, cast

from PyQt6.QtCore import (
    Qt, QThread, QThreadPool, QRunnable, pyqtSignal, pyqtSlot, QObject, QUrl, QSize, QTimer,
    QMutex, QMetaObject, Q_ARG
)
from PyQt6.QtGui import (
    QIcon, QPixmap, QFont, QFontDatabase, QDesktopServices, QAction, QColor
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QListWidget, QListWidgetItem, QFrame, QSplitter,
    QProgressBar, QComboBox, QCheckBox, QMessageBox, QFileDialog, QMenu,
    QScrollArea, QStatusBar, QToolBar, QToolButton, QSizePolicy, QTabWidget
)

from ytdownload.api.youtube import YouTubeAPI, Video, Playlist
from ytdownload.services.downloader import (
    DownloadManager, DownloadTask, DownloadType, DownloadProgress
)
from ytdownload.gui.video_item import VideoItemWidget
from ytdownload.gui.playlist_item import PlaylistItemWidget
from ytdownload.gui.download_item import DownloadItemWidget
from ytdownload.utils.helpers import (
    format_duration, format_view_count, is_valid_youtube_url, is_youtube_channel_url,
    get_app_config_dir
)
from ytdownload.utils.logger import get_logger

# Get logger
logger = get_logger()


class WorkerSignals(QObject):
    """Defines the signals available for a worker thread."""
    
    started = pyqtSignal()
    finished = pyqtSignal()
    error = pyqtSignal(str)
    result = pyqtSignal(object)
    progress = pyqtSignal(int, str)  # progress percentage, status message


class Worker(QRunnable):
    """Worker thread for running background tasks."""
    
    def __init__(self, fn, *args, **kwargs):
        """
        Initialize the worker.

        Args:
            fn: Function to run
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
        """
        super(Worker, self).__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @pyqtSlot()
    def run(self):
        """Execute the function with provided arguments."""
        try:
            self.signals.started.emit()
            result = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(result)
        except Exception as e:
            logger.error(f"Worker error: {str(e)}", exc_info=True)
            self.signals.error.emit(str(e))
        finally:
            self.signals.finished.emit()


class AsyncExecutor(QThread):
    """Thread for running async code in Qt."""
    
    def __init__(self, coro):
        """
        Initialize the thread with a coroutine.

        Args:
            coro: Coroutine to run
        """
        super().__init__()
        self.coro = coro

    def run(self):
        """Execute the coroutine in a new event loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.coro)
        loop.close()


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        """Initialize the main window and UI components."""
        super().__init__()
        
        logger.info("Initializing main window")
        self.setWindowTitle("YouTube Downloader")
        self.setMinimumSize(1000, 700)
        
        # Initialize instance variables
        self.videos: List[Video] = []
        self.playlists: List[Playlist] = []
        self.current_playlist_videos: List[Video] = []
        self.current_playlist_id: Optional[str] = None
        self.download_manager = DownloadManager(
            progress_callback=self.handle_download_progress
        )
        self.thread_pool = QThreadPool()
        self.selected_items: Set[str] = set()  # Set of selected video IDs
        
        # Thread synchronization
        self.progress_queue = queue.Queue()  # Thread-safe queue for progress updates
        self.progress_timer = QTimer(self)  # Timer to process updates on the main thread
        self.progress_timer.timeout.connect(self.process_progress_updates)
        self.progress_timer.start(100)  # Process updates every 100ms
        
        # Mutex for protecting counter updates
        self.download_mutex = QMutex()
        
        # Set up UI
        self.init_ui()
        self.setup_menu()
        self.setup_stylesheet()
        
        # Status bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready")
        
        # Loading indicator inside status bar
        self.loading_indicator = QProgressBar()
        self.loading_indicator.setFixedWidth(150)
        self.loading_indicator.setRange(0, 0)  # Indeterminate progress
        self.loading_indicator.setVisible(False)
        self.status_bar.addPermanentWidget(self.loading_indicator)
        
        # Status timer for animated messages
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status_animation)
        self.status_animation_count = 0
        self.status_base_message = ""
        
        logger.info("Main window initialized")

    def init_ui(self):
        """Set up the user interface components."""
        logger.debug("Setting up UI components")
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Search section
        search_layout = QHBoxLayout()
        search_layout.setSpacing(10)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Enter YouTube channel URL...")
        self.search_input.setMinimumHeight(40)
        self.search_input.returnPressed.connect(self.search_channel)
        
        self.search_button = QPushButton("Search")
        self.search_button.setMinimumHeight(40)
        self.search_button.setMinimumWidth(100)
        self.search_button.clicked.connect(self.search_channel)
        
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.search_button, 0)
        
        main_layout.addLayout(search_layout)
        
        # Progress indicator for search
        self.search_progress = QProgressBar()
        self.search_progress.setVisible(False)
        self.search_progress.setRange(0, 100)
        self.search_progress.setValue(0)
        self.search_progress.setFormat("%p% - %v")
        main_layout.addWidget(self.search_progress)
        
        # Search status label
        self.search_status = QLabel()
        self.search_status.setVisible(False)
        self.search_status.setStyleSheet("color: #666; font-style: italic;")
        main_layout.addWidget(self.search_status)
        
        # Splitter for channel content and downloads
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        
        # Channel content section (with tabs for videos and playlists)
        channel_content_widget = QWidget()
        channel_content_layout = QVBoxLayout(channel_content_widget)
        channel_content_layout.setContentsMargins(0, 0, 0, 0)
        channel_content_layout.setSpacing(10)
        
        # Channel header
        channel_header = QWidget()
        channel_header_layout = QHBoxLayout(channel_header)
        channel_header_layout.setContentsMargins(0, 0, 0, 0)
        
        self.content_title = QLabel("Channel Content")
        self.content_title.setObjectName("section-title")
        channel_header_layout.addWidget(self.content_title)
        
        self.channel_info_label = QLabel()
        self.channel_info_label.setStyleSheet("color: #666;")
        channel_header_layout.addWidget(self.channel_info_label)
        
        channel_header_layout.addStretch()
        
        channel_content_layout.addWidget(channel_header)
        
        # Tabs for videos and playlists
        self.content_tabs = QTabWidget()
        self.content_tabs.setDocumentMode(True)
        
        # Videos tab
        self.videos_tab = QWidget()
        videos_tab_layout = QVBoxLayout(self.videos_tab)
        videos_tab_layout.setContentsMargins(0, 10, 0, 0)
        videos_tab_layout.setSpacing(10)
        
        # Videos controls
        videos_controls = QWidget()
        videos_controls_layout = QHBoxLayout(videos_controls)
        videos_controls_layout.setContentsMargins(0, 0, 0, 0)
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.select_all_videos)
        videos_controls_layout.addWidget(self.select_all_btn)
        
        self.deselect_all_btn = QPushButton("Deselect All")
        self.deselect_all_btn.clicked.connect(self.deselect_all_videos)
        videos_controls_layout.addWidget(self.deselect_all_btn)
        
        videos_controls_layout.addStretch()
        
        videos_tab_layout.addWidget(videos_controls)
        
        # Videos list
        self.videos_list = QListWidget()
        self.videos_list.setObjectName("videos-list")
        self.videos_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.videos_list.setSpacing(5)
        self.videos_list.setUniformItemSizes(True)
        
        # Placeholder label for empty list
        self.videos_placeholder = QLabel("No videos to display. Enter a YouTube channel URL and click Search.")
        self.videos_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.videos_placeholder.setStyleSheet("color: #999; font-size: 14px; padding: 20px;")
        
        videos_tab_layout.addWidget(self.videos_placeholder)
        videos_tab_layout.addWidget(self.videos_list)
        self.videos_list.setVisible(False)
        
        # Playlists tab
        self.playlists_tab = QWidget()
        playlists_tab_layout = QVBoxLayout(self.playlists_tab)
        playlists_tab_layout.setContentsMargins(0, 10, 0, 0)
        playlists_tab_layout.setSpacing(10)
        
        # Back button for playlist videos view
        self.back_to_playlists_btn = QPushButton("← Back to Playlists")
        self.back_to_playlists_btn.clicked.connect(self.show_playlists)
        self.back_to_playlists_btn.setVisible(False)
        self.back_to_playlists_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #0071e3;
                border: none;
                padding: 4px 8px;
                font-weight: bold;
                text-align: left;
            }
            QPushButton:hover {
                color: #0077ed;
                text-decoration: underline;
            }
        """)
        
        # Playlist controls (for when viewing a playlist's videos)
        self.playlist_controls = QWidget()
        playlist_controls_layout = QHBoxLayout(self.playlist_controls)
        playlist_controls_layout.setContentsMargins(0, 0, 0, 0)
        
        self.playlist_select_all_btn = QPushButton("Select All")
        self.playlist_select_all_btn.clicked.connect(self.select_all_videos)
        playlist_controls_layout.addWidget(self.playlist_select_all_btn)
        
        self.playlist_deselect_all_btn = QPushButton("Deselect All")
        self.playlist_deselect_all_btn.clicked.connect(self.deselect_all_videos)
        playlist_controls_layout.addWidget(self.playlist_deselect_all_btn)
        
        playlist_controls_layout.addStretch()
        
        # Initially hide these controls
        self.playlist_controls.setVisible(False)
        
        playlists_tab_layout.addWidget(self.back_to_playlists_btn)
        playlists_tab_layout.addWidget(self.playlist_controls)
        
        # Playlists list
        self.playlists_list = QListWidget()
        self.playlists_list.setObjectName("playlists-list")
        self.playlists_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.playlists_list.setSpacing(5)
        self.playlists_list.setUniformItemSizes(True)
        
        # Placeholder label for empty playlists
        self.playlists_placeholder = QLabel("No playlists found for this channel.")
        self.playlists_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.playlists_placeholder.setStyleSheet("color: #999; font-size: 14px; padding: 20px;")
        
        playlists_tab_layout.addWidget(self.playlists_placeholder)
        playlists_tab_layout.addWidget(self.playlists_list)
        self.playlists_list.setVisible(False)
        
        # Add tabs to tab widget
        self.content_tabs.addTab(self.videos_tab, "Videos")
        self.content_tabs.addTab(self.playlists_tab, "Playlists")
        
        # Connect tab changed signal
        self.content_tabs.currentChanged.connect(self.handle_tab_change)
        
        channel_content_layout.addWidget(self.content_tabs)
        
        # Download options
        download_options = QWidget()
        download_options_layout = QHBoxLayout(download_options)
        download_options_layout.setContentsMargins(0, 0, 0, 0)
        
        # Content type selection
        self.content_type = QComboBox()
        self.content_type.addItems(["Video", "Audio Only", "Transcript"])
        download_options_layout.addWidget(QLabel("Download:"))
        download_options_layout.addWidget(self.content_type)
        
        download_options_layout.addStretch()
        
        # Download button
        self.download_button = QPushButton("Download Selected")
        self.download_button.setMinimumHeight(36)
        self.download_button.setMinimumWidth(150)
        self.download_button.clicked.connect(self.download_selected)
        download_options_layout.addWidget(self.download_button)
        
        channel_content_layout.addWidget(download_options)
        
        # Add channel content to splitter
        splitter.addWidget(channel_content_widget)
        
        # Downloads section
        downloads_widget = QWidget()
        downloads_layout = QVBoxLayout(downloads_widget)
        downloads_layout.setContentsMargins(0, 0, 0, 0)
        downloads_layout.setSpacing(10)
        
        # Downloads header
        downloads_header = QWidget()
        downloads_header_layout = QHBoxLayout(downloads_header)
        downloads_header_layout.setContentsMargins(0, 0, 0, 0)
        
        downloads_title = QLabel("Downloads")
        downloads_title.setObjectName("section-title")
        downloads_header_layout.addWidget(downloads_title)
        
        downloads_header_layout.addStretch()
        
        # Clear completed button
        self.clear_completed_btn = QPushButton("Clear Completed")
        self.clear_completed_btn.clicked.connect(self.clear_completed_downloads)
        downloads_header_layout.addWidget(self.clear_completed_btn)
        
        downloads_layout.addWidget(downloads_header)
        
        # Downloads list
        self.downloads_list = QListWidget()
        self.downloads_list.setObjectName("downloads-list")
        self.downloads_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.downloads_list.setSpacing(5)
        
        # Placeholder for downloads
        self.downloads_placeholder = QLabel("No downloads yet. Select videos to download.")
        self.downloads_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.downloads_placeholder.setStyleSheet("color: #999; font-size: 14px; padding: 20px;")
        
        downloads_layout.addWidget(self.downloads_placeholder)
        downloads_layout.addWidget(self.downloads_list)
        self.downloads_list.setVisible(False)
        
        # Add downloads section to splitter
        splitter.addWidget(downloads_widget)
        
        # Set initial splitter sizes (2/3 for videos, 1/3 for downloads)
        splitter.setSizes([int(self.height() * 0.7), int(self.height() * 0.3)])
        
        main_layout.addWidget(splitter, 1)
        
        # Initial state
        self.update_ui_state()
        logger.debug("UI components setup completed")

    def setup_menu(self):
        """Set up the application menu."""
        logger.debug("Setting up application menu")
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("File")
        
        open_folder_action = QAction("Open Download Folder", self)
        open_folder_action.triggered.connect(self.open_download_folder)
        file_menu.addAction(open_folder_action)
        
        view_logs_action = QAction("View Logs", self)
        view_logs_action.triggered.connect(self.open_logs_folder)
        file_menu.addAction(view_logs_action)
        
        file_menu.addSeparator()
        
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        file_menu.addAction(quit_action)
        
        # Help menu
        help_menu = menu_bar.addMenu("Help")
        
        about_action = QAction("About", self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)
        
        logger.debug("Application menu setup completed")

    def setup_stylesheet(self):
        """Set up application styling."""
        logger.debug("Setting up application stylesheet")
        self.setStyleSheet("""
            QMainWindow {
                background-color: #f5f5f7;
            }
            
            QLabel#section-title {
                font-size: 18px;
                font-weight: bold;
                color: #333;
                margin-bottom: 5px;
            }
            
            QLineEdit {
                padding: 8px;
                border-radius: 6px;
                border: 1px solid #d1d1d6;
                background-color: white;
                font-size: 14px;
            }
            
            QLineEdit:focus {
                border: 1px solid #0071e3;
            }
            
            QPushButton {
                background-color: #0071e3;
                color: white;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: bold;
                border: none;
            }
            
            QPushButton:hover {
                background-color: #0077ed;
            }
            
            QPushButton:pressed {
                background-color: #005bbf;
            }
            
            QPushButton:disabled {
                background-color: #a1a1a6;
            }
            
            QListWidget {
                background-color: white;
                border-radius: 8px;
                border: 1px solid #d1d1d6;
                padding: 5px;
            }
            
            QProgressBar {
                border: 1px solid #d1d1d6;
                border-radius: 5px;
                background-color: #f0f0f0;
                text-align: center;
                height: 16px;
            }
            
            QProgressBar::chunk {
                background-color: #34c759;
                border-radius: 5px;
            }
            
            QComboBox {
                padding: 8px;
                border-radius: 6px;
                border: 1px solid #d1d1d6;
                background-color: white;
                min-width: 150px;
            }
            
            QStatusBar {
                background-color: #f5f5f7;
                color: #666;
            }
            
            QMenuBar {
                background-color: #f5f5f7;
                border-bottom: 1px solid #d1d1d6;
            }
            
            QMenuBar::item {
                padding: 4px 10px;
                background-color: transparent;
            }
            
            QMenuBar::item:selected {
                background-color: #0071e3;
                color: white;
                border-radius: 4px;
            }
            
            QTabWidget::pane {
                border: 1px solid #d1d1d6;
                border-radius: 8px;
                background-color: white;
            }
            
            QTabBar::tab {
                background-color: #f0f0f0;
                border: 1px solid #d1d1d6;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 8px 16px;
                margin-right: 2px;
                color: #333;
            }
            
            QTabBar::tab:selected {
                background-color: white;
                border-bottom-color: white;
                font-weight: bold;
            }
            
            QTabBar::tab:hover:!selected {
                background-color: #e0e0e0;
            }
        """)
        logger.debug("Application stylesheet setup completed")

    def search_channel(self):
        """Search for YouTube channel videos and playlists."""
        channel_url = self.search_input.text().strip()
        logger.info(f"Searching for channel: {channel_url}")
        
        if not channel_url:
            self.show_error("Please enter a YouTube channel URL")
            return
            
        if not is_valid_youtube_url(channel_url) and not channel_url.startswith('@'):
            self.show_error("Invalid YouTube URL")
            return
            
        if not is_youtube_channel_url(channel_url) and not channel_url.startswith('@'):
            self.show_error("Please enter a channel URL, not a video URL")
            return
        
        # Reset state and update UI to show loading state
        self.videos_list.clear()
        self.playlists_list.clear()
        self.videos_list.setVisible(False)
        self.playlists_list.setVisible(False)
        self.videos_placeholder.setText("Searching for videos... This may take a moment.")
        self.videos_placeholder.setVisible(True)
        self.playlists_placeholder.setText("Searching for playlists...")
        self.playlists_placeholder.setVisible(True)
        self.selected_items.clear()
        self.update_ui_state(is_loading=True)
        
        # Reset timeout tracker
        self.search_start_time = time.time()
        
        # Reset loaded flags
        self.videos_loaded = False
        self.playlists_loaded = False
        
        # Show loading indicators
        self.search_progress.setVisible(True)
        self.search_progress.setValue(0)
        self.search_status.setText("Initializing search...")
        self.search_status.setVisible(True)
        self.loading_indicator.setVisible(True)
        
        # Start animated status message
        self.status_base_message = "Fetching channel content"
        self.start_status_animation()
        
        # Execute videos search in a worker thread
        self.search_videos(channel_url)
        
        # Execute playlists search in another worker thread
        self.search_playlists(channel_url)
        
        # Set a safety timeout to ensure search always completes
        QTimer.singleShot(30000, self.handle_search_timeout)

    def search_videos(self, channel_url: str):
        """
        Search for YouTube channel videos.
        
        Args:
            channel_url: URL of the YouTube channel
        """
        logger.info(f"Starting search for videos: {channel_url}")
        
        worker = Worker(YouTubeAPI.get_channel_videos, channel_url)
        worker.signals.started.connect(self.handle_videos_search_started)
        worker.signals.result.connect(self.handle_videos_loaded)
        worker.signals.error.connect(self.handle_videos_search_error)
        
        # Start a timer to update progress (simulated since we don't have real progress)
        self.videos_progress_timer = QTimer()
        self.videos_progress_timer.timeout.connect(self.update_search_progress)
        self.videos_progress_timer.start(500)  # Update every 500ms
        
        self.thread_pool.start(worker)

    def search_playlists(self, channel_url: str):
        """
        Search for YouTube channel playlists.
        
        Args:
            channel_url: URL of the YouTube channel
        """
        logger.info(f"Starting search for playlists: {channel_url}")
        
        # Set the playlist tab message
        self.playlists_placeholder.setText("Searching for playlists...\nThis may take longer for channels with many playlists.")
        
        worker = Worker(YouTubeAPI.get_channel_playlists, channel_url)
        worker.signals.started.connect(self.handle_playlists_search_started)
        worker.signals.result.connect(self.handle_playlists_loaded)
        worker.signals.error.connect(self.handle_playlists_search_error)
        
        # Start a timer to update the loading message to keep user informed
        self.playlist_message_timer = QTimer()
        self.playlist_message_count = 0
        self.playlist_message_timer.timeout.connect(self.update_playlist_loading_message)
        self.playlist_message_timer.start(3000)  # Update every 3 seconds
        
        self.thread_pool.start(worker)

    def handle_videos_search_started(self):
        """Handle videos search start."""
        logger.info("Video search started")
        self.search_status.setText("Connecting to YouTube...")

    def handle_playlists_search_started(self):
        """Handle playlists search start."""
        logger.info("Playlists search started")
        self.status_bar.showMessage("Searching for playlists...")

    def update_search_progress(self):
        """Update the search progress bar (simulated progress)."""
        # Check timeout first, independently of progress updates
        if hasattr(self, 'search_start_time'):
            elapsed_time = time.time() - self.search_start_time
            # Add more logging to track timeouts
            if elapsed_time > 30:  # 30 second timeout
                logger.warning(f"Search timeout reached after {elapsed_time:.1f} seconds, completing search")
                self.complete_search()
                return
        
        # Regular progress updates
        current = self.search_progress.value()
        if current < 95:  # Allow going closer to 100%
            new_value = min(current + 3, 95)  # Slower progress to give more time
            self.search_progress.setValue(new_value)
            
            # Update status message based on progress
            if new_value < 30:
                self.search_status.setText("Connecting to YouTube...")
            elif new_value < 60:
                self.search_status.setText("Retrieving channel information...")
            else:
                self.search_status.setText("Processing videos and playlists...")
                
    def complete_search(self):
        """Complete the search process and update UI."""
        # Set loaded flags to ensure completion
        self.videos_loaded = True
        self.playlists_loaded = True
        
        # Complete the progress
        self.search_progress.setValue(100)
        self.search_status.setText("Search completed")
        
        # Stop timers
        if hasattr(self, 'videos_progress_timer') and self.videos_progress_timer.isActive():
            self.videos_progress_timer.stop()
        if hasattr(self, 'playlist_message_timer') and self.playlist_message_timer.isActive():
            self.playlist_message_timer.stop()
            
        # Hide loading indicators after a delay
        QTimer.singleShot(1000, lambda: self.search_progress.setVisible(False))
        QTimer.singleShot(1000, lambda: self.search_status.setVisible(False))
        self.stop_status_animation()
        self.loading_indicator.setVisible(False)
        
        self.update_ui_state(is_loading=False)

    def handle_videos_loaded(self, videos: List[Video]):
        """
        Handle loaded videos from the search.

        Args:
            videos: List of videos from the channel
        """
        logger.info(f"Videos loaded: {len(videos)} videos found")
        self.videos = videos
        self.videos_list.clear()
        self.selected_items.clear()
        
        # Stop the progress timer
        if hasattr(self, 'videos_progress_timer'):
            self.videos_progress_timer.stop()
        
        # Set videos loaded flag
        self.videos_loaded = True
        
        # Complete the progress when both playlists and videos are loaded
        if hasattr(self, 'playlists_loaded') and self.playlists_loaded:
            self.complete_search()
        
        if not videos:
            logger.warning("No videos found in the channel")
            self.status_bar.showMessage("No videos found in this channel")
            self.videos_placeholder.setText("No videos found in this channel. Try another channel.")
            self.videos_placeholder.setVisible(True)
            self.videos_list.setVisible(False)
        else:
            # Update channel info
            if videos:
                self.channel_info_label.setText(f" - {videos[0].channel_title} ({len(videos)} videos)")
            
            # Show video list, hide placeholder
            self.videos_placeholder.setVisible(False)
            self.videos_list.setVisible(True)
                
            # Add videos to the list
            logger.debug("Adding videos to the list")
            for video in videos:
                item = QListWidgetItem()
                widget = VideoItemWidget(video, self.select_video_item)
                item.setSizeHint(widget.sizeHint())
                self.videos_list.addItem(item)
                self.videos_list.setItemWidget(item, widget)
        
        self.update_ui_state()
        self.status_bar.showMessage(f"Found {len(videos)} videos. Select videos to download.")

    def handle_playlists_loaded(self, playlists: List[Playlist]):
        """
        Handle loaded playlists from the search.

        Args:
            playlists: List of playlists from the channel
        """
        logger.info(f"Playlists loaded: {len(playlists)} playlists found")
        
        # Stop the playlist message timer if it's running
        if hasattr(self, 'playlist_message_timer') and self.playlist_message_timer.isActive():
            self.playlist_message_timer.stop()
            
        self.playlists = playlists
        self.playlists_list.clear()
        
        # Set playlists loaded flag
        self.playlists_loaded = True
        
        # Complete the progress when both playlists and videos are loaded
        if hasattr(self, 'videos_loaded') and self.videos_loaded:
            self.complete_search()
        
        if not playlists:
            logger.warning("No playlists found in the channel")
            self.playlists_placeholder.setText("No playlists found in this channel.\n\nNote: Some channels hide their playlists\nor YouTube may limit access to them.")
            self.playlists_placeholder.setVisible(True)
            self.playlists_list.setVisible(False)
        else:
            # Show playlists list, hide placeholder
            self.playlists_placeholder.setVisible(False)
            self.playlists_list.setVisible(True)
                
            # Add playlists to the list
            logger.debug("Adding playlists to the list")
            for playlist in playlists:
                item = QListWidgetItem()
                widget = PlaylistItemWidget(playlist, self.view_playlist)
                item.setSizeHint(widget.sizeHint())
                self.playlists_list.addItem(item)
                self.playlists_list.setItemWidget(item, widget)
        
        self.update_ui_state()
        
        if self.content_tabs.currentIndex() == 1:  # Playlists tab
            self.status_bar.showMessage(f"Found {len(playlists)} playlists.")

    def handle_videos_search_error(self, error_msg: str):
        """
        Handle videos search errors.

        Args:
            error_msg: Error message to display
        """
        logger.error(f"Videos search error: {error_msg}")
        
        # Stop the progress timer
        if hasattr(self, 'videos_progress_timer'):
            self.videos_progress_timer.stop()
            
        # Update UI to show error
        self.search_progress.setValue(self.search_progress.value())  # Keep current progress
        self.search_status.setText(f"Error: {error_msg}")
        self.search_status.setStyleSheet("color: #ff3b30; font-style: italic;")
        
        # Set videos loaded flag even on error
        self.videos_loaded = True
        
        # Complete search if playlists are also loaded
        if hasattr(self, 'playlists_loaded') and self.playlists_loaded:
            self.complete_search()
        
        # Show error message
        self.show_error(f"Error searching for videos: {error_msg}")
        self.status_bar.showMessage("Error searching for videos")
        
        # Update placeholder
        self.videos_placeholder.setText("Error searching for videos. Please try again.")
        self.videos_placeholder.setVisible(True)
        self.videos_list.setVisible(False)
        
        self.update_ui_state()

    def handle_playlists_search_error(self, error_msg: str):
        """
        Handle playlists search errors.

        Args:
            error_msg: Error message to display
        """
        logger.error(f"Playlists search error: {error_msg}")
        
        # Stop the playlist message timer if it's running
        if hasattr(self, 'playlist_message_timer') and self.playlist_message_timer.isActive():
            self.playlist_message_timer.stop()
        
        # Set playlists loaded flag even on error
        self.playlists_loaded = True
        
        # Complete search if videos are also loaded
        if hasattr(self, 'videos_loaded') and self.videos_loaded:
            self.complete_search()
        
        # Update placeholder with error information and suggestions
        self.playlists_placeholder.setText(
            "Could not load playlists.\n\n"
            f"Error: {error_msg}\n\n"
            "This might be due to:\n"
            "• YouTube API limitations\n"
            "• Network connectivity issues\n"
            "• Channel has restricted access to playlists\n\n"
            "Try again later or try a different channel."
        )
        self.playlists_placeholder.setVisible(True)
        self.playlists_list.setVisible(False)
        
        self.update_ui_state()
        
        if self.content_tabs.currentIndex() == 1:  # Playlists tab
            self.status_bar.showMessage("Error searching for playlists")

    def view_playlist(self, playlist_id: str):
        """
        Display videos from a specific playlist.
        
        Args:
            playlist_id: Playlist ID to view
        """
        # Get playlist title
        playlist_title = "Loading playlist..."
        for p in self.playlists:
            if p.playlist_id == playlist_id:
                playlist_title = p.title
                break
        
        logger.info(f"Viewing playlist: {playlist_title} ({playlist_id})")
        
        # Update UI to show loading state
        self.playlists_list.setVisible(False)
        self.playlists_placeholder.setVisible(True)
        self.playlists_placeholder.setText("Loading playlist videos...")
        
        # Show back button and playlist controls
        self.back_to_playlists_btn.setVisible(True)
        self.playlist_controls.setVisible(True)
        
        # Store current playlist ID
        self.current_playlist_id = playlist_id
        
        # Show loading indicator
        if hasattr(self, 'loading_indicator'):
            self.loading_indicator.setVisible(True)
        
        # Update status bar
        self.status_bar.showMessage("Loading playlist videos...")
        
        # Execute playlist videos search in a worker thread
        worker = Worker(YouTubeAPI.get_playlist_videos, playlist_id)
        worker.signals.result.connect(
            lambda videos: self.handle_playlist_videos_loaded(videos, playlist_title)
        )
        worker.signals.error.connect(self.handle_playlist_videos_error)
        
        # Start the worker
        self.thread_pool.start(worker)

    def show_playlists(self):
        """
        Show the main playlists list (exit playlist view).
        """
        logger.info("Showing main playlists list")
        
        # Reset UI
        self.back_to_playlists_btn.setVisible(False)
        self.playlist_controls.setVisible(False)
        self.current_playlist_id = None
        
        # Clear the list
        self.playlists_list.clear()
        
        # Show playlists if available, or show placeholder
        if self.playlists and len(self.playlists) > 0:
            self.playlists_placeholder.setVisible(False)
            self.playlists_list.setVisible(True)
            
            # Add playlists to the list
            for playlist in self.playlists:
                item = QListWidgetItem()
                widget = PlaylistItemWidget(playlist, self.view_playlist)
                item.setSizeHint(widget.sizeHint())
                self.playlists_list.addItem(item)
                self.playlists_list.setItemWidget(item, widget)
        else:
            self.playlists_list.setVisible(False)
            self.playlists_placeholder.setVisible(True)

    def select_video_item(self, video_id: str, selected: bool):
        """
        Handle selection of a video item in the videos tab.

        Args:
            video_id: YouTube video ID
            selected: Whether the video is selected
        """
        if selected:
            self.selected_items.add(video_id)
            logger.debug(f"Video selected: {video_id}")
        else:
            self.selected_items.discard(video_id)
            logger.debug(f"Video deselected: {video_id}")
        
        self.status_bar.showMessage(f"{len(self.selected_items)} videos selected")
        self.update_ui_state()

    def select_playlist_video_item(self, video_id: str, selected: bool):
        """
        Handle selection of a video item in the playlists tab.

        Args:
            video_id: YouTube video ID
            selected: Whether the video is selected
        """
        if selected:
            self.selected_items.add(video_id)
            logger.debug(f"Playlist video selected: {video_id}")
        else:
            self.selected_items.discard(video_id)
            logger.debug(f"Playlist video deselected: {video_id}")
        
        self.status_bar.showMessage(f"{len(self.selected_items)} videos selected")
        self.update_ui_state()

    def handle_tab_change(self, index: int):
        """
        Handle tab changes between Videos and Playlists.
        
        Args:
            index: Tab index
        """
        logger.debug(f"Tab changed to index: {index}")
        
        if index == 0:  # Videos tab
            self.status_bar.showMessage(f"Found {len(self.videos)} videos. Select videos to download.")
            # Enable select/deselect all buttons
            self.select_all_btn.setEnabled(len(self.videos) > 0)
            self.deselect_all_btn.setEnabled(len(self.selected_items) > 0)
        else:  # Playlists tab
            if self.current_playlist_id:
                self.status_bar.showMessage(f"Loaded {len(self.current_playlist_videos)} videos from playlist.")
            else:
                self.status_bar.showMessage(f"Found {len(self.playlists)} playlists.")

    def select_all_videos(self):
        """Select all videos in the current view."""
        logger.info("Selecting all videos")
        
        if self.content_tabs.currentIndex() == 0:  # Videos tab
            # Add all video IDs to selected_items
            for video in self.videos:
                self.selected_items.add(video.video_id)
            
            # Update checkboxes in videos list
            for i in range(self.videos_list.count()):
                item = self.videos_list.item(i)
                widget = self.videos_list.itemWidget(item)
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(True)
                    
            self.status_bar.showMessage(f"Selected all {len(self.videos)} videos")
            
        elif self.current_playlist_id:  # Playlist videos view
            # Add all playlist video IDs to selected_items
            video_count = 0
            for video in self.current_playlist_videos:
                self.selected_items.add(video.video_id)
                video_count += 1
            
            # Update checkboxes in playlists list
            for i in range(self.playlists_list.count()):
                item = self.playlists_list.item(i)
                widget = self.playlists_list.itemWidget(item)
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(True)
            
            logger.debug(f"Selected {video_count} videos from playlist")
            self.status_bar.showMessage(f"Selected all {video_count} videos from playlist")
        
        self.update_ui_state()

    def deselect_all_videos(self):
        """Deselect all videos in the current view."""
        logger.info("Deselecting all videos")
        
        if self.content_tabs.currentIndex() == 0:  # Videos tab
            # Get all video IDs in the main list
            video_ids = {video.video_id for video in self.videos}
            
            # Remove these IDs from the selected items
            self.selected_items -= video_ids
            
            # Update checkboxes in videos list
            for i in range(self.videos_list.count()):
                item = self.videos_list.item(i)
                widget = self.videos_list.itemWidget(item)
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(False)
                    
            self.status_bar.showMessage("Deselected all videos")
            
        elif self.current_playlist_id:  # Playlist videos view
            # Get all video IDs in the current playlist
            video_ids = {video.video_id for video in self.current_playlist_videos}
            
            # Remove these IDs from the selected items
            self.selected_items -= video_ids
            
            # Update checkboxes in playlists list
            for i in range(self.playlists_list.count()):
                item = self.playlists_list.item(i)
                widget = self.playlists_list.itemWidget(item)
                if hasattr(widget, 'set_selected'):
                    widget.set_selected(False)
                    
            self.status_bar.showMessage("Deselected all videos from playlist")
        
        self.update_ui_state()

    def download_selected(self):
        """Download the selected videos."""
        if not self.selected_items:
            self.show_error("No videos selected")
            return
        
        logger.info(f"Starting download of {len(self.selected_items)} selected videos")
        
        # Determine download type
        download_type_index = self.content_type.currentIndex()
        download_type_name = self.content_type.currentText()
        if download_type_index == 0:
            download_type = DownloadType.VIDEO
        elif download_type_index == 1:
            download_type = DownloadType.AUDIO
        else:
            download_type = DownloadType.TRANSCRIPT
        
        logger.info(f"Download type: {download_type_name}")
        
        # Create download tasks
        tasks = []
        
        # Log selection info
        logger.debug(f"Selected items count: {len(self.selected_items)}")
        logger.debug(f"Current playlist ID: {self.current_playlist_id}")
        
        # Add from main videos list
        main_videos_added = 0
        for video in self.videos:
            if video.video_id in self.selected_items:
                task = DownloadTask(
                    video_id=video.video_id,
                    title=video.title,
                    download_type=download_type,
                    output_path=""  # Will be set by the download manager
                )
                tasks.append(task)
                main_videos_added += 1
                logger.debug(f"Adding download task for main video: {video.title}")
            
        logger.info(f"Added {main_videos_added} tasks from main videos list")
        
        # Add from playlist videos if viewing a playlist
        playlist_videos_added = 0
        if self.current_playlist_id:
            logger.debug(f"Processing playlist videos. Total playlist videos: {len(self.current_playlist_videos)}")
            for video in self.current_playlist_videos:
                # Check if video ID is in selected items and not already added
                is_selected = video.video_id in self.selected_items
                is_unique = not any(t.video_id == video.video_id for t in tasks)
                
                logger.debug(f"Playlist video '{video.title}': Selected={is_selected}, Unique={is_unique}")
                
                if is_selected and is_unique:
                    task = DownloadTask(
                        video_id=video.video_id,
                        title=video.title,
                        download_type=download_type,
                        output_path=""  # Will be set by the download manager
                    )
                    tasks.append(task)
                    playlist_videos_added += 1
                    logger.debug(f"Adding download task for playlist video: {video.title}")
            
            logger.info(f"Added {playlist_videos_added} tasks from playlist videos")
        
        # Summary log
        logger.info(f"Total download tasks created: {len(tasks)}")
        
        # Show download list and hide placeholder
        self.downloads_placeholder.setVisible(False)
        self.downloads_list.setVisible(True)
        
        # Initialize download tracking with mutex protection
        self.download_mutex.lock()
        try:
            self.total_downloads = len(tasks)
            self.completed_downloads = 0
            self.error_downloads = 0
            self.canceled_downloads = 0
            
            # Update status on the main thread
            status_message = f"Starting download of {len(tasks)} items... (0/{self.total_downloads} completed)"
            QMetaObject.invokeMethod(
                self.status_bar, 
                "showMessage", 
                Qt.ConnectionType.QueuedConnection,
                Q_ARG(str, status_message)
            )
        finally:
            self.download_mutex.unlock()
        
        # Add to download manager
        self.download_manager.add_tasks(tasks)
        
        # Start downloads
        # Keep a reference to the executor to prevent premature garbage collection
        self.download_executor = AsyncExecutor(self.download_manager.start_downloads())
        self.download_executor.start()

    def handle_download_progress(self, progress: DownloadProgress):
        """
        Handle download progress updates by pushing them to the thread-safe queue.

        Args:
            progress: Download progress information
        """
        try:
            # Push the progress update to the queue for processing on the main thread
            self.progress_queue.put(progress)
        except Exception as e:
            logger.error(f"Error queueing progress update: {str(e)}", exc_info=True)

    def update_download_status(self):
        """Update the status bar with overall download progress."""
        # Use mutex for thread-safe access to counters
        self.download_mutex.lock()
        try:
            if hasattr(self, 'total_downloads') and self.total_downloads > 0:
                finished = self.completed_downloads + self.error_downloads + self.canceled_downloads
                active = self.total_downloads - finished
                
                # Use invokeMethod to ensure UI updates happen on the main thread
                if active > 0:
                    if self.error_downloads > 0 and self.canceled_downloads > 0:
                        status_message = (
                            f"Downloading {active} of {self.total_downloads} items... "
                            f"({self.completed_downloads} completed, {self.error_downloads} failed, "
                            f"{self.canceled_downloads} canceled)"
                        )
                    elif self.error_downloads > 0:
                        status_message = (
                            f"Downloading {active} of {self.total_downloads} items... "
                            f"({self.completed_downloads} completed, {self.error_downloads} failed)"
                        )
                    elif self.canceled_downloads > 0:
                        status_message = (
                            f"Downloading {active} of {self.total_downloads} items... "
                            f"({self.completed_downloads} completed, {self.canceled_downloads} canceled)"
                        )
                    else:
                        status_message = (
                            f"Downloading {active} of {self.total_downloads} items... "
                            f"({self.completed_downloads}/{self.total_downloads} completed)"
                        )
                else:
                    # All downloads have finished
                    if self.error_downloads > 0 or self.canceled_downloads > 0:
                        status_message = (
                            f"All downloads finished: {self.completed_downloads} completed, "
                            f"{self.error_downloads} failed, {self.canceled_downloads} canceled"
                        )
                    else:
                        status_message = f"All {self.total_downloads} downloads completed successfully!"
                
                # Update status bar on main thread
                QMetaObject.invokeMethod(
                    self.status_bar, 
                    "showMessage", 
                    Qt.ConnectionType.QueuedConnection,
                    Q_ARG(str, status_message)
                )
        finally:
            self.download_mutex.unlock()

    def cancel_download(self, video_id: str):
        """
        Cancel a download.

        Args:
            video_id: YouTube video ID
        """
        logger.info(f"Canceling download for video: {video_id}")
        
        # Use mutex to protect counter updates
        self.download_mutex.lock()
        try:
            # Get the current status from the widget to avoid double counting
            for i in range(self.downloads_list.count()):
                item = self.downloads_list.item(i)
                widget = cast(DownloadItemWidget, self.downloads_list.itemWidget(item))
                if widget.video_id == video_id:
                    # Only count as canceled if it wasn't already completed or errored
                    if not widget.is_completed and not widget.has_error and not widget.is_canceled:
                        if hasattr(self, 'canceled_downloads'):
                            self.canceled_downloads += 1
                            self.update_download_status()
                    break
        finally:
            self.download_mutex.unlock()
        
        self.download_manager.cancel_download(video_id)

    def clear_completed_downloads(self):
        """Clear completed downloads from the list."""
        logger.info("Clearing completed downloads")
        items_to_remove = []
        
        # Find completed items
        for i in range(self.downloads_list.count()):
            item = self.downloads_list.item(i)
            widget = cast(DownloadItemWidget, self.downloads_list.itemWidget(item))
            
            if widget.is_completed or widget.is_canceled or widget.has_error:
                items_to_remove.append(i)
        
        # Use mutex for thread-safe updates to counters
        self.download_mutex.lock()
        try:
            # Remove items in reverse order (to not mess up indices)
            for i in sorted(items_to_remove, reverse=True):
                self.downloads_list.takeItem(i)
                
            # Show placeholder if list is empty
            if self.downloads_list.count() == 0:
                self.downloads_list.setVisible(False)
                self.downloads_placeholder.setVisible(True)
                
                # Reset counters if all downloads are cleared
                if hasattr(self, 'total_downloads'):
                    self.total_downloads = 0
                    self.completed_downloads = 0
                    self.error_downloads = 0
                    self.canceled_downloads = 0
                
            # Update status bar
            cleared_count = len(items_to_remove)
            if self.downloads_list.count() == 0:
                self.status_bar.showMessage(f"Cleared {cleared_count} completed downloads. Ready for new downloads.")
            else:
                # Count remaining active downloads
                active_downloads = 0
                for i in range(self.downloads_list.count()):
                    item = self.downloads_list.item(i)
                    widget = cast(DownloadItemWidget, self.downloads_list.itemWidget(item))
                    if not (widget.is_completed or widget.is_canceled or widget.has_error):
                        active_downloads += 1
                
                self.status_bar.showMessage(f"Cleared {cleared_count} completed downloads. {active_downloads} downloads still in progress.")
                
                # Update the tracking counters to reflect only the items that remain in the list
                if hasattr(self, 'total_downloads'):
                    # Recalculate counters based on remaining items
                    remaining_total = 0
                    remaining_completed = 0
                    remaining_errors = 0
                    remaining_canceled = 0
                    
                    for i in range(self.downloads_list.count()):
                        item = self.downloads_list.item(i)
                        widget = cast(DownloadItemWidget, self.downloads_list.itemWidget(item))
                        remaining_total += 1
                        if widget.is_completed:
                            remaining_completed += 1
                        if widget.has_error:
                            remaining_errors += 1
                        if widget.is_canceled:
                            remaining_canceled += 1
                    
                    self.total_downloads = remaining_total
                    self.completed_downloads = remaining_completed
                    self.error_downloads = remaining_errors
                    self.canceled_downloads = remaining_canceled
                    
                    # Update status display with new counts
                    if remaining_total > 0:
                        self.update_download_status()
        finally:
            self.download_mutex.unlock()

    def update_ui_state(self, is_loading: bool = False):
        """
        Update UI components based on current state.

        Args:
            is_loading: Whether the app is currently loading data
        """
        has_videos = len(self.videos) > 0
        has_playlists = len(self.playlists) > 0
        has_selected = len(self.selected_items) > 0
        
        self.search_button.setEnabled(not is_loading)
        self.search_input.setEnabled(not is_loading)
        self.content_type.setEnabled(has_selected and not is_loading)
        self.download_button.setEnabled(has_selected and not is_loading)
        
        # Update select/deselect buttons based on active tab
        if self.content_tabs.currentIndex() == 0:  # Videos tab
            self.select_all_btn.setEnabled(has_videos and not is_loading)
            self.deselect_all_btn.setEnabled(has_videos and has_selected and not is_loading)
        else:  # Playlists tab
            # Only enable select/deselect all if viewing a playlist's videos
            has_playlist_videos = len(self.current_playlist_videos) > 0
            self.select_all_btn.setEnabled(has_playlist_videos and not is_loading)
            self.deselect_all_btn.setEnabled(has_playlist_videos and has_selected and not is_loading)
        
        # Update the downloads section
        has_downloads = self.downloads_list.count() > 0
        self.clear_completed_btn.setEnabled(has_downloads)
        
        # Update status message if loading
        if is_loading:
            self.status_bar.showMessage("Loading...")

    def start_status_animation(self):
        """Start animated status message."""
        self.status_animation_count = 0
        self.status_timer.start(500)  # Update every 500ms

    def stop_status_animation(self):
        """Stop animated status message."""
        self.status_timer.stop()
        self.status_bar.showMessage("Ready")

    def update_status_animation(self):
        """Update the animated status message."""
        dots = "." * (self.status_animation_count % 4)
        self.status_bar.showMessage(f"{self.status_base_message}{dots}")
        self.status_animation_count += 1

    def open_download_folder(self):
        """Open the downloads folder in the file explorer."""
        logger.info("Opening download folder")
        download_path = os.path.abspath(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "downloads"))
        QDesktopServices.openUrl(QUrl.fromLocalFile(download_path))

    def open_logs_folder(self):
        """Open the logs folder in the file explorer."""
        logger.info("Opening logs folder")
        logs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(logs_dir))

    def show_about(self):
        """Show the about dialog."""
        logger.info("Showing about dialog")
        QMessageBox.about(
            self,
            "About YouTube Downloader",
            "YouTube Downloader 0.1.0\n\n"
            "A beautiful application to download content from YouTube channels.\n\n"
            "Created with PyQt6 and Python."
        )

    def show_error(self, message: str):
        """
        Show an error message box.

        Args:
            message: Error message to display
        """
        logger.error(f"Error dialog: {message}")
        QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event):
        """
        Handle window close event.

        Args:
            event: Close event
        """
        logger.info("Application closing")
        
        # Stop progress timer
        if hasattr(self, 'progress_timer') and self.progress_timer.isActive():
            self.progress_timer.stop()
            
        # Process any remaining items in the queue
        try:
            while not self.progress_queue.empty():
                self.progress_queue.get_nowait()
                self.progress_queue.task_done()
        except Exception as e:
            logger.warning(f"Error draining progress queue: {str(e)}")
            
        # Wait for all running downloads to complete
        if hasattr(self, 'download_executor') and self.download_executor.isRunning():
            logger.info("Waiting for downloads to complete before closing...")
            self.download_executor.wait(2000)  # Wait up to 2 seconds
        
        # Make sure all threads are stopped
        self.thread_pool.waitForDone(2000)  # Wait up to 2 seconds
        
        event.accept()

    def update_playlist_loading_message(self):
        """Update the playlist loading message to keep user informed of progress."""
        messages = [
            "Searching for playlists...\nThis may take longer for channels with many playlists.",
            "Still searching for playlists...\nYouTube can be slow to respond with playlist data.",
            "Continuing playlist search...\nLarge channels can have many playlists to process.",
            "Loading playlists...\nWe're working on it!",
            "Almost there...\nProcessing playlist information."
        ]
        
        if self.playlist_message_count < len(messages):
            self.playlists_placeholder.setText(messages[self.playlist_message_count])
            self.playlist_message_count += 1
        else:
            # After cycling through all messages, just use a rotating dot animation
            dots = "." * (self.playlist_message_count % 4)
            self.playlists_placeholder.setText(f"Still loading playlists{dots}\nThis channel may have many playlists.")
            self.playlist_message_count += 1

    def handle_search_timeout(self):
        """Handle case when search takes too long and needs to be completed."""
        if hasattr(self, 'videos_loaded') and hasattr(self, 'playlists_loaded'):
            if not self.videos_loaded or not self.playlists_loaded:
                logger.warning("Search timeout safety triggered - forcing completion")
                self.complete_search() 

    def handle_playlist_videos_loaded(self, videos: List[Video], playlist_title: str):
        """
        Handle loaded playlist videos.
        
        Args:
            videos: List of videos from the playlist
            playlist_title: The title of the playlist
        """
        logger.info(f"Playlist videos loaded: {len(videos)} videos found")
        
        # Store current playlist videos
        self.current_playlist_videos = videos
        
        # Clear playlists list
        self.playlists_list.clear()
        
        # Update title if we have a content title widget
        if hasattr(self, 'content_title'):
            self.content_title.setText(f"Playlist: {playlist_title}")
        
        # Stop loading indicator if we have one
        if hasattr(self, 'loading_indicator') and self.loading_indicator.isVisible():
            self.loading_indicator.setVisible(False)
        
        if not videos or len(videos) == 0:
            logger.warning("No videos found in the playlist")
            self.playlists_placeholder.setText("No videos found in this playlist.")
            self.playlists_placeholder.setVisible(True)
            self.playlists_list.setVisible(False)
        else:
            # Show playlist videos, hide placeholder
            self.playlists_placeholder.setVisible(False)
            self.playlists_list.setVisible(True)
            
            # Add videos to the list
            logger.debug(f"Adding {len(videos)} playlist videos to the list")
            for video in videos:
                item = QListWidgetItem()
                widget = VideoItemWidget(video, self.select_playlist_video_item)
                item.setSizeHint(widget.sizeHint())
                self.playlists_list.addItem(item)
                self.playlists_list.setItemWidget(item, widget)
        
        # Update UI state
        self.update_ui_state()
        self.status_bar.showMessage(f"Loaded {len(videos)} videos from playlist.")

    def handle_playlist_videos_error(self, error_msg: str):
        """
        Handle errors when loading videos for a specific playlist.

        Args:
            error_msg: Error message to display
        """
        logger.error(f"Playlist videos loading error: {error_msg}")
        
        # Hide loading indicator
        if hasattr(self, 'loading_indicator') and self.loading_indicator.isVisible():
            self.loading_indicator.setVisible(False)
            
        # Reset current playlist videos list
        self.current_playlist_videos = []
        
        # Update placeholder with error information and user guidance
        self.playlists_placeholder.setText(
            "Could not load playlist videos.\n\n"
            f"Error: {error_msg}\n\n"
            "This might be due to:\n"
            "• YouTube API limitations\n"
            "• Video availability restrictions\n"
            "• Network connectivity issues\n\n"
            "Try again later or try a different playlist."
        )
        self.playlists_placeholder.setVisible(True)
        self.playlists_list.setVisible(False)
        
        # Show error message
        self.show_error(f"Error loading playlist videos: {error_msg}")
        self.status_bar.showMessage("Error loading playlist videos")
        
        self.update_ui_state() 

    def handle_api_error(self, error_msg: str):
        """
        Handle general API errors.

        Args:
            error_msg: Error message to display
        """
        logger.error(f"API error: {error_msg}")
        
        # Hide loading indicator
        if hasattr(self, 'loading_indicator') and self.loading_indicator.isVisible():
            self.loading_indicator.setVisible(False)
            
        # Show error message
        self.show_error(f"Error: {error_msg}")
        self.status_bar.showMessage("Error occurred while loading content")
        
    def process_progress_updates(self):
        """
        Process download progress updates from the queue on the main thread.
        This ensures thread-safe UI updates.
        """
        try:
            # Process all available updates in the queue
            while not self.progress_queue.empty():
                progress = self.progress_queue.get_nowait()
                self._update_download_progress_ui(progress)
                self.progress_queue.task_done()
        except Exception as e:
            logger.error(f"Error processing progress updates: {str(e)}", exc_info=True)
            
    def _update_download_progress_ui(self, progress: DownloadProgress):
        """
        Update the UI with download progress information.
        This method is called on the main thread to ensure thread safety.
        
        Args:
            progress: Download progress information
        """
        # Find if we already have a widget for this download
        found = False
        for i in range(self.downloads_list.count()):
            item = self.downloads_list.item(i)
            widget = cast(DownloadItemWidget, self.downloads_list.itemWidget(item))
            if widget.video_id == progress.video_id:
                # Check if this item just completed, has an error, or was canceled
                was_complete = widget.is_completed
                was_error = widget.has_error
                was_canceled = widget.is_canceled
                
                # Update the widget
                widget.update_progress(progress)
                
                # Use mutex to protect counter updates
                self.download_mutex.lock()
                try:
                    # Check if status changed to completed, error, or canceled
                    if not was_complete and widget.is_completed:
                        if hasattr(self, 'completed_downloads'):
                            self.completed_downloads += 1
                            self.update_download_status()
                            
                    if not was_error and widget.has_error:
                        if hasattr(self, 'error_downloads'):
                            self.error_downloads += 1
                            self.update_download_status()
                            
                    if not was_canceled and widget.is_canceled:
                        if hasattr(self, 'canceled_downloads'):
                            self.canceled_downloads += 1
                            self.update_download_status()
                finally:
                    self.download_mutex.unlock()
                
                found = True
                break
        
        # If not found, create a new widget
        if not found:
            logger.debug(f"Creating new download item widget for: {progress.title}")
            item = QListWidgetItem()
            widget = DownloadItemWidget(progress, self.cancel_download)
            item.setSizeHint(widget.sizeHint())
            self.downloads_list.addItem(item)
            self.downloads_list.setItemWidget(item, widget)
            
            # Use mutex to protect counter updates
            self.download_mutex.lock()
            try:
                # Check initial state
                if progress.is_complete:
                    if hasattr(self, 'completed_downloads'):
                        self.completed_downloads += 1
                        self.update_download_status()
                elif progress.error:
                    if hasattr(self, 'error_downloads'):
                        self.error_downloads += 1
                        self.update_download_status()
                elif progress.status == "Canceled":
                    if hasattr(self, 'canceled_downloads'):
                        self.canceled_downloads += 1
                        self.update_download_status()
            finally:
                self.download_mutex.unlock()
        