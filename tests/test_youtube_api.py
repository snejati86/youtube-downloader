"""
Tests for the YouTube API module.

This module contains tests for the YouTube API functionality.
"""
from typing import List, Dict, Any, TYPE_CHECKING
import pytest
from unittest.mock import MagicMock, patch

from ytdownload.api.youtube import YouTubeAPI, Video

if TYPE_CHECKING:
    from _pytest.monkeypatch import MonkeyPatch
    from pytest_mock.plugin import MockerFixture


def test_extract_channel_id() -> None:
    """Test extracting channel ID from various URL formats."""
    # Test with direct channel URL
    with patch('pytube.Channel') as mock_channel:
        mock_channel_instance = MagicMock()
        mock_channel_instance.channel_id = "UC123456789"
        mock_channel.return_value = mock_channel_instance
        
        channel_id = YouTubeAPI.extract_channel_id("https://youtube.com/channel/UC123456789")
        assert channel_id == "UC123456789"
        mock_channel.assert_called_once_with("https://youtube.com/channel/UC123456789")
    
    # Test with custom URL
    with patch('pytube.Channel') as mock_channel:
        mock_channel_instance = MagicMock()
        mock_channel_instance.channel_id = "UC123456789"
        mock_channel.return_value = mock_channel_instance
        
        channel_id = YouTubeAPI.extract_channel_id("https://youtube.com/c/channelname")
        assert channel_id == "UC123456789"
        mock_channel.assert_called_once_with("https://youtube.com/c/channelname")
    
    # Test with handle URL
    with patch('pytube.Channel') as mock_channel:
        mock_channel_instance = MagicMock()
        mock_channel_instance.channel_id = "UC123456789"
        mock_channel.return_value = mock_channel_instance
        
        channel_id = YouTubeAPI.extract_channel_id("https://youtube.com/@channelname")
        assert channel_id == "UC123456789"
        mock_channel.assert_called_once_with("https://youtube.com/@channelname")
    
    # Test with invalid URL
    channel_id = YouTubeAPI.extract_channel_id("https://youtube.com/watch?v=VIDEO_ID")
    assert channel_id is None


def test_get_channel_videos(mocker: "MockerFixture") -> None:
    """
    Test retrieving videos from a channel.
    
    Args:
        mocker: pytest-mock fixture
    """
    # Mock pytube.Channel
    mock_channel = MagicMock()
    mock_channel.channel_name = "Test Channel"
    
    # Mock video objects
    mock_video1 = MagicMock()
    mock_video1.video_id = "video1"
    mock_video1.title = "Test Video 1"
    mock_video1.thumbnail_url = "https://example.com/thumb1.jpg"
    mock_video1.publish_date = "2022-01-01"
    mock_video1.description = "Test description 1"
    
    mock_video2 = MagicMock()
    mock_video2.video_id = "video2"
    mock_video2.title = "Test Video 2"
    mock_video2.thumbnail_url = "https://example.com/thumb2.jpg"
    mock_video2.publish_date = "2022-01-02"
    mock_video2.description = "Test description 2"
    
    mock_channel.videos = [mock_video1, mock_video2]
    
    # Mock YoutubeDL
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.side_effect = [
        {"duration": 120, "view_count": 1000},
        {"duration": 240, "view_count": 2000}
    ]
    
    mock_ydl = mocker.patch('ytdownload.api.youtube.YoutubeDL')
    mock_ydl.return_value.__enter__.return_value = mock_ydl_instance
    
    # Mock pytube.Channel creation
    mocker.patch('pytube.Channel', return_value=mock_channel)
    
    # Call the function
    videos = YouTubeAPI.get_channel_videos("https://youtube.com/channel/UC123456789")
    
    # Assertions
    assert len(videos) == 2
    
    assert videos[0].video_id == "video1"
    assert videos[0].title == "Test Video 1"
    assert videos[0].duration == 120
    assert videos[0].view_count == 1000
    
    assert videos[1].video_id == "video2"
    assert videos[1].title == "Test Video 2"
    assert videos[1].duration == 240
    assert videos[1].view_count == 2000


def test_get_video_info(mocker: "MockerFixture") -> None:
    """
    Test retrieving detailed information about a video.
    
    Args:
        mocker: pytest-mock fixture
    """
    # Mock YoutubeDL
    mock_info = {
        "title": "Test Video",
        "duration": 120,
        "view_count": 1000,
        "description": "Test description"
    }
    
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.return_value = mock_info
    
    mock_ydl = mocker.patch('ytdownload.api.youtube.YoutubeDL')
    mock_ydl.return_value.__enter__.return_value = mock_ydl_instance
    
    # Call the function
    info = YouTubeAPI.get_video_info("video1")
    
    # Assertions
    assert info == mock_info
    mock_ydl_instance.extract_info.assert_called_once_with(
        "https://youtube.com/watch?v=video1", download=False
    )


def test_get_video_info_error(mocker: "MockerFixture") -> None:
    """
    Test error handling when retrieving video information.
    
    Args:
        mocker: pytest-mock fixture
    """
    # Mock YoutubeDL to raise an exception
    mock_ydl_instance = MagicMock()
    mock_ydl_instance.extract_info.side_effect = Exception("Test error")
    
    mock_ydl = mocker.patch('ytdownload.api.youtube.YoutubeDL')
    mock_ydl.return_value.__enter__.return_value = mock_ydl_instance
    
    # Mock print to avoid output during test
    mocker.patch('builtins.print')
    
    # Call the function
    info = YouTubeAPI.get_video_info("video1")
    
    # Assertions
    assert info is None 