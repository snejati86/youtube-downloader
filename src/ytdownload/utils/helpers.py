"""
Helper utilities for the YouTube Downloader application.

This module provides various helper functions for formatting, validation, and other utilities.
"""
import os
import re
import time
from typing import Dict, List, Optional, Tuple, Union


def format_duration(seconds: int) -> str:
    """
    Format duration in seconds to a human-readable format.

    Args:
        seconds: Duration in seconds

    Returns:
        str: Formatted duration string (HH:MM:SS or MM:SS)
    """
    if seconds < 0:
        return "00:00"
        
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    if hours > 0:
        return f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
    else:
        return f"{int(minutes):02d}:{int(seconds):02d}"


def format_file_size(bytes_size: int) -> str:
    """
    Format file size in bytes to a human-readable format.

    Args:
        bytes_size: Size in bytes

    Returns:
        str: Formatted size string with appropriate unit
    """
    if bytes_size < 0:
        return "0 B"
        
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(bytes_size)
    unit_index = 0
    
    while size >= 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    
    return f"{size:.2f} {units[unit_index]}"


def format_view_count(count: int) -> str:
    """
    Format view count to a human-readable format.

    Args:
        count: Number of views

    Returns:
        str: Formatted view count with appropriate suffix
    """
    if count < 0:
        return "0 views"
        
    if count < 1000:
        return f"{count} views"
    elif count < 1000000:
        return f"{count / 1000:.1f}K views"
    else:
        return f"{count / 1000000:.1f}M views"


def is_valid_youtube_url(url: str) -> bool:
    """
    Check if a URL is a valid YouTube URL.

    Args:
        url: URL to check

    Returns:
        bool: True if the URL is a valid YouTube URL, False otherwise
    """
    youtube_regex = (
        r'(?:https?:\/\/)?(?:www\.)?'
        r'(?:youtube\.com|youtu\.be)'
        r'(?:\/(?:watch\?v=|channel\/|c\/|user\/|@))?'
        r'[^\s]+'
    )
    return bool(re.match(youtube_regex, url))


def is_youtube_channel_url(url: str) -> bool:
    """
    Check if a URL is a YouTube channel URL.

    Args:
        url: URL to check

    Returns:
        bool: True if the URL is a YouTube channel URL, False otherwise
    """
    channel_regex = (
        r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/'
        r'(?:channel\/|c\/|user\/|@)'
        r'[^\s\/]+'
    )
    return bool(re.match(channel_regex, url))


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to be safe for all operating systems.

    Args:
        filename: Original filename

    Returns:
        str: Sanitized filename
    """
    # Replace invalid characters with underscores
    invalid_chars = r'[<>:"/\\|?*]'
    sanitized = re.sub(invalid_chars, '_', filename)
    
    # Trim whitespace and dots at the beginning and end
    sanitized = sanitized.strip().strip('.')
    
    # Use a placeholder if the filename is empty after sanitization
    if not sanitized:
        sanitized = "untitled"
    
    # Truncate if too long (max 255 bytes for most filesystems)
    max_length = 255
    if len(sanitized.encode('utf-8')) > max_length:
        while len(sanitized.encode('utf-8')) > max_length:
            sanitized = sanitized[:-1]
    
    return sanitized


def get_app_config_dir() -> str:
    """
    Get the application configuration directory.

    Returns:
        str: Path to the configuration directory
    """
    home = os.path.expanduser("~")
    
    if os.name == 'nt':  # Windows
        app_dir = os.path.join(home, 'AppData', 'Local', 'YTDownload')
    elif os.name == 'posix':  # macOS/Linux
        if os.path.exists(os.path.join(home, 'Library')):  # macOS
            app_dir = os.path.join(home, 'Library', 'Application Support', 'YTDownload')
        else:  # Linux
            app_dir = os.path.join(home, '.config', 'ytdownload')
    else:
        app_dir = os.path.join(home, '.ytdownload')
    
    os.makedirs(app_dir, exist_ok=True)
    return app_dir 