"""
Downloader service for YouTube content.

This module provides functionality to download video, audio, and transcripts
from YouTube with maximum concurrency.
"""
import asyncio
import os
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple, Union

from yt_dlp import YoutubeDL
import logging

logger = logging.getLogger(__name__)


class DownloadType(Enum):
    """Enum representing download content types."""
    VIDEO = auto()
    AUDIO = auto()
    TRANSCRIPT = auto()


@dataclass
class DownloadTask:
    """
    Represents a download task for a specific video.

    Attributes:
        video_id: YouTube video ID
        title: Title of the video
        download_type: Type of content to download
        output_path: Path where the downloaded content should be saved
    """
    video_id: str
    title: str
    download_type: DownloadType
    output_path: str


@dataclass
class DownloadProgress:
    """
    Represents the current progress of a download.

    Attributes:
        video_id: YouTube video ID
        title: Title of the video
        progress: Download progress percentage (0-100)
        status: Current status message
        is_complete: Whether the download is complete
        error: Error message if download failed
    """
    video_id: str
    title: str
    progress: float = 0.0
    status: str = "Waiting"
    is_complete: bool = False
    error: Optional[str] = None


class DownloadManager:
    """Manages concurrent downloads of YouTube content."""

    def __init__(
        self, 
        max_concurrent_downloads: int = 5,
        download_dir: str = "downloads",
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None
    ):
        """
        Initialize the download manager.

        Args:
            max_concurrent_downloads: Maximum number of concurrent downloads
            download_dir: Directory to save downloads
            progress_callback: Callback function for progress updates
        """
        self.max_concurrent_downloads = max_concurrent_downloads
        self.download_dir = Path(download_dir)
        self.progress_callback = progress_callback
        self.download_queue: List[DownloadTask] = []
        self.active_downloads: Set[str] = set()
        self.download_progress: Dict[str, DownloadProgress] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent_downloads)
        
        # Create download directory if it doesn't exist
        os.makedirs(self.download_dir, exist_ok=True)
        
        # Create subdirectories for different content types
        for content_type in ["video", "audio", "transcript"]:
            os.makedirs(self.download_dir / content_type, exist_ok=True)

    def add_task(self, task: DownloadTask) -> None:
        """
        Add a download task to the queue.

        Args:
            task: Download task to add
        """
        self.download_queue.append(task)
        self.download_progress[task.video_id] = DownloadProgress(
            video_id=task.video_id,
            title=task.title
        )
        
        if self.progress_callback:
            self.progress_callback(self.download_progress[task.video_id])

    def add_tasks(self, tasks: List[DownloadTask]) -> None:
        """
        Add multiple download tasks to the queue.

        Args:
            tasks: List of download tasks to add
        """
        for task in tasks:
            self.add_task(task)

    async def download_video(self, task: DownloadTask) -> None:
        """
        Download a video using yt-dlp.

        Args:
            task: Download task containing video details
        """
        video_url = f"https://youtube.com/watch?v={task.video_id}"
        progress = self.download_progress[task.video_id]
        progress.status = "Downloading"
        
        if self.progress_callback:
            self.progress_callback(progress)
        
        try:
            output_template = os.path.join(task.output_path, '%(title)s.%(ext)s')
            
            # Configure yt-dlp options based on download type
            ydl_opts = {
                'quiet': True,
                'progress_hooks': [lambda d: self._progress_hook(d, task.video_id)],
                'outtmpl': output_template,
            }
            
            if task.download_type == DownloadType.VIDEO:
                ydl_opts.update({
                    'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
                })
            elif task.download_type == DownloadType.AUDIO:
                ydl_opts.update({
                    'format': 'bestaudio[ext=m4a]/bestaudio/best',
                    'postprocessors': [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }],
                })
            elif task.download_type == DownloadType.TRANSCRIPT:
                ydl_opts.update({
                    'skip_download': True,
                    'writesubtitles': True,
                    'writeautomaticsub': True,
                    'subtitleslangs': ['en'],
                    'subtitlesformat': 'vtt',  # Using vtt instead of srt as it's more commonly available
                })
            
            async with self.semaphore:
                self.active_downloads.add(task.video_id)
                
                # Update progress to show startup
                self._update_progress(task.video_id, 10, "Starting download...")
                
                # Special handling for transcripts since they don't generate normal progress updates
                if task.download_type == DownloadType.TRANSCRIPT:
                    # Update progress to show we're working
                    self._update_progress(task.video_id, 25, "Fetching transcript...")
                    
                    # Special progress updates for transcript downloads
                    # since they don't trigger normal progress hooks
                    def transcript_progress_updater():
                        stages = [
                            (40, "Requesting subtitles..."),
                            (60, "Processing transcript..."),
                            (80, "Finalizing transcript..."),
                        ]
                        for percent, message in stages:
                            self._update_progress(task.video_id, percent, message)
                            
                    # Run transcript progress updater in a separate thread
                    import threading
                    progress_thread = threading.Thread(target=transcript_progress_updater)
                    progress_thread.daemon = True
                    progress_thread.start()
                
                try:
                    # Run yt-dlp in a separate thread to avoid blocking the event loop
                    await asyncio.get_event_loop().run_in_executor(
                        None, 
                        lambda: YoutubeDL(ydl_opts).download([video_url])
                    )
                    
                    # For transcripts, verify files were actually created
                    if task.download_type == DownloadType.TRANSCRIPT:
                        self._update_progress(task.video_id, 90, "Verifying transcript...")
                        
                        # Check if any subtitle files were created
                        subtitle_found = False
                        possible_extensions = ['.vtt', '.srt', '.ttml', '.sbv', '.srv3', '.srv2', '.srv1']
                        
                        # Prepare base filename safely
                        try:
                            info_opts = dict(ydl_opts)
                            info_opts.update({'skip_download': True, 'writesubtitles': False, 'writeautomaticsub': False})
                            info = YoutubeDL(info_opts).extract_info(video_url, download=False)
                            base_filename = YoutubeDL(ydl_opts).prepare_filename(info)
                            base_path = os.path.splitext(base_filename)[0]
                            
                            # Fallback if the above didn't work
                            if not base_path:
                                base_path = os.path.join(task.output_path, task.title)
                        except Exception as e:
                            logger.warning(f"Error preparing filename: {str(e)}")
                            # Fallback to a best guess
                            base_path = os.path.join(task.output_path, task.title)
                            
                        # Look for any subtitle files that might have been created
                        for ext in possible_extensions:
                            for lang in ['en', 'en-US', 'en-GB']:
                                subtitle_path = f"{base_path}.{lang}{ext}"
                                if os.path.exists(subtitle_path):
                                    logger.info(f"Found subtitle file: {subtitle_path}")
                                    subtitle_found = True
                                    break
                                    
                            # Also check without language code
                            subtitle_path = f"{base_path}{ext}"
                            if os.path.exists(subtitle_path):
                                logger.info(f"Found subtitle file: {subtitle_path}")
                                subtitle_found = True
                                break
                        
                        # Check the whole directory as a last resort
                        if not subtitle_found:
                            logger.warning(f"No direct subtitle match found, checking directory: {task.output_path}")
                            for filename in os.listdir(task.output_path):
                                file_path = os.path.join(task.output_path, filename)
                                if os.path.isfile(file_path):
                                    file_lower = filename.lower()
                                    # Check if file appears to be a subtitle related to this video
                                    if any(ext in file_lower for ext in possible_extensions) and (
                                           task.video_id in file_lower or 
                                           task.title.lower() in file_lower):
                                        logger.info(f"Found potential subtitle file: {file_path}")
                                        subtitle_found = True
                                        break
                        
                        if not subtitle_found:
                            raise Exception("No transcript was available for this video")
                except Exception as e:
                    logger.error(f"Error downloading transcript: {str(e)}")
                    raise Exception(f"Failed to download transcript: {str(e)}")
                
                progress.is_complete = True
                progress.progress = 100.0
                progress.status = "Complete"
                
                if self.progress_callback:
                    self.progress_callback(progress)
                    
        except Exception as e:
            logger.error(f"Download error for {task.title}: {str(e)}")
            progress.error = str(e)
            progress.status = "Error"
            if self.progress_callback:
                self.progress_callback(progress)
        finally:
            self.active_downloads.discard(task.video_id)

    def _progress_hook(self, d: Dict, video_id: str) -> None:
        """
        Handle progress updates from yt-dlp.

        Args:
            d: Progress dictionary from yt-dlp
            video_id: Video ID for the current download
        """
        if video_id not in self.download_progress:
            return
            
        progress = self.download_progress[video_id]
        
        if d['status'] == 'downloading':
            try:
                if 'total_bytes' in d and d.get('total_bytes', 0) > 0:
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes', 1)  # Avoid division by zero
                    if downloaded is not None and total is not None:
                        pct = (downloaded / total) * 100
                        progress.progress = pct
                elif 'total_bytes_estimate' in d and d.get('total_bytes_estimate', 0) > 0:
                    downloaded = d.get('downloaded_bytes', 0)
                    total = d.get('total_bytes_estimate', 1)  # Avoid division by zero
                    if downloaded is not None and total is not None:
                        pct = (downloaded / total) * 100
                        progress.progress = pct
                
                # Always set a status even if percentage calculation failed
                percent_str = d.get('_percent_str', '?%')
                progress.status = f"Downloading ({percent_str})"
            except (TypeError, ValueError) as e:
                # Handle math errors gracefully
                logger.warning(f"Error calculating progress: {str(e)}")
                progress.status = f"Downloading..."
            
        elif d['status'] == 'finished':
            progress.status = "Processing"
            progress.progress = 95.0  # Not quite done, still processing
            
        elif d['status'] == 'error':
            progress.status = "Error"
            progress.error = d.get('error', "Unknown error")
            
        if self.progress_callback:
            # Call progress callback in a thread-safe way
            # We're potentially in a worker thread here, not the UI thread
            try:
                self.progress_callback(progress)
            except Exception as e:
                # Log but don't halt the download process if UI callback fails
                logger.error(f"Error calling progress callback: {str(e)}")

    async def start_downloads(self) -> None:
        """Start downloading all queued tasks concurrently."""
        tasks = []
        for task in self.download_queue:
            # Set appropriate output path based on download type
            if task.download_type == DownloadType.VIDEO:
                output_path = os.path.join(self.download_dir, "video")
            elif task.download_type == DownloadType.AUDIO:
                output_path = os.path.join(self.download_dir, "audio")
            elif task.download_type == DownloadType.TRANSCRIPT:
                output_path = os.path.join(self.download_dir, "transcript")
            else:
                output_path = self.download_dir
                
            task.output_path = output_path
            tasks.append(self.download_video(task))
            
        self.download_queue.clear()
        await asyncio.gather(*tasks)

    def get_progress(self, video_id: str) -> Optional[DownloadProgress]:
        """
        Get the current progress for a specific download.

        Args:
            video_id: YouTube video ID

        Returns:
            Optional[DownloadProgress]: Progress information or None if not found
        """
        return self.download_progress.get(video_id)

    def get_all_progress(self) -> List[DownloadProgress]:
        """
        Get progress for all downloads.

        Returns:
            List[DownloadProgress]: List of all download progress objects
        """
        return list(self.download_progress.values())

    def cancel_download(self, video_id: str) -> bool:
        """
        Cancel a download if it's in the queue or in progress.

        Args:
            video_id: YouTube video ID to cancel

        Returns:
            bool: True if the download was canceled, False otherwise
        """
        # Remove from queue if present
        for i, task in enumerate(self.download_queue):
            if task.video_id == video_id:
                del self.download_queue[i]
                if video_id in self.download_progress:
                    progress = self.download_progress[video_id]
                    progress.status = "Canceled"
                    if self.progress_callback:
                        self.progress_callback(progress)
                return True
                
        # Mark as canceled if active (actual cancellation is complex)
        if video_id in self.active_downloads:
            if video_id in self.download_progress:
                progress = self.download_progress[video_id]
                progress.status = "Canceling"
                if self.progress_callback:
                    self.progress_callback(progress)
            return True
            
        return False 

    def _update_progress(self, video_id: str, percent: float, status: str) -> None:
        """
        Update progress for a video download.
        
        Args:
            video_id: Video ID
            percent: Percentage complete
            status: Status message
        """
        if video_id in self.download_progress:
            try:
                progress = self.download_progress[video_id]
                progress.progress = percent
                progress.status = status
                
                if self.progress_callback:
                    # Call progress callback in a thread-safe way
                    try:
                        self.progress_callback(progress)
                    except Exception as e:
                        # Log but don't halt the download process if UI callback fails
                        logger.error(f"Error calling progress callback: {str(e)}")
            except Exception as e:
                logger.error(f"Error updating progress: {str(e)}") 