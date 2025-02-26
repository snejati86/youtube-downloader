"""
YouTube API module for fetching channel data and video information.

This module provides functionality to interact with YouTube data
using pytube and yt-dlp libraries.
"""
import re
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union, Any

import pytube
from yt_dlp import YoutubeDL

from ytdownload.utils.logger import get_logger

# Get logger
logger = get_logger()


@dataclass
class Video:
    """
    Representation of a YouTube video.

    Attributes:
        video_id: Unique identifier for the video
        title: Title of the video
        thumbnail_url: URL to the video thumbnail
        channel_title: Name of the channel
        duration: Duration in seconds
        publish_date: Publication date
        description: Video description
        view_count: Number of views
    """
    video_id: str
    title: str
    thumbnail_url: str
    channel_title: str
    duration: int
    publish_date: str
    description: str
    view_count: int


@dataclass
class Playlist:
    """
    Representation of a YouTube playlist.

    Attributes:
        playlist_id: Unique identifier for the playlist
        title: Title of the playlist
        thumbnail_url: URL to the playlist thumbnail
        channel_title: Name of the channel
        video_count: Number of videos in the playlist
        description: Playlist description
        last_updated: Last update date
    """
    playlist_id: str
    title: str
    thumbnail_url: str
    channel_title: str
    video_count: int
    description: str
    last_updated: str


class YouTubeAPI:
    """Handles interactions with the YouTube API and data extraction."""

    @staticmethod
    def extract_channel_id(url: str) -> Optional[str]:
        """
        Extract the channel ID from a YouTube URL.

        Args:
            url: YouTube channel URL in various formats

        Returns:
            str: Channel ID if found, None otherwise
        """
        logger.info(f"Extracting channel ID from URL: {url}")
        
        # Clean up URL (remove leading/trailing spaces, normalize @)
        url = url.strip()
        if url.startswith('@'):
            url = f"https://youtube.com/{url}"
            
        # Handle channel URLs
        channel_id_match = re.search(r'(?:youtube\.com/channel/|youtube\.com/c/|youtube\.com/@)([\w-]+)', url)
        if channel_id_match:
            channel_name = channel_id_match.group(1)
            logger.info(f"Found channel identifier: {channel_name}")
            
            try:
                if channel_name.startswith('@'):
                    logger.debug(f"Handling as handle: {channel_name}")
                    channel = pytube.Channel(f"https://youtube.com/{channel_name}")
                else:
                    # Check if it's a custom URL or a channel ID
                    if re.match(r'^UC[\w-]{22}$', channel_name):
                        logger.debug(f"Handling as channel ID: {channel_name}")
                        channel = pytube.Channel(f"https://youtube.com/channel/{channel_name}")
                    else:
                        logger.debug(f"Handling as custom URL: {channel_name}")
                        channel = pytube.Channel(f"https://youtube.com/c/{channel_name}")
                
                channel_id = channel.channel_id
                logger.info(f"Resolved channel ID: {channel_id}")
                return channel_id
            except Exception as e:
                logger.error(f"Error extracting channel ID: {str(e)}", exc_info=True)
                return None
                
        logger.warning(f"Could not extract channel ID from URL: {url}")
        return None

    @staticmethod
    def get_channel_videos(channel_url: str) -> List[Video]:
        """
        Fetch videos from a given YouTube channel.

        Args:
            channel_url: URL of the YouTube channel

        Returns:
            List[Video]: List of videos from the channel
        """
        videos = []
        logger.info(f"Fetching videos from channel: {channel_url}")
        
        try:
            start_time = time.time()
            
            # First, extract the channel ID
            channel_id = YouTubeAPI.extract_channel_id(channel_url)
            if not channel_id:
                logger.error("Could not extract channel ID for videos")
                return []
                
            logger.info(f"Using channel ID: {channel_id} to fetch videos")
            
            # Use yt-dlp to get channel videos
            # This is more reliable than pytube's approach
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'lazy_playlist': False,
                'ignoreerrors': True,
                'no_warnings': True,
                'retries': 5,
                'playlistend': 50  # Limit to 50 videos for performance
            }
            
            # Get channel name first
            try:
                channel = pytube.Channel(channel_url)
                channel_name = channel.channel_name
                logger.info(f"Channel name: {channel_name}")
            except Exception as e:
                logger.warning(f"Could not get channel name, using ID instead: {str(e)}")
                channel_name = f"Channel {channel_id}"
            
            # Use videos URL instead of the channel URL directly
            videos_url = f"https://www.youtube.com/channel/{channel_id}/videos"
            logger.info(f"Fetching videos from: {videos_url}")
            
            with YoutubeDL(ydl_opts) as ydl:
                channel_info = ydl.extract_info(videos_url, download=False)
                
                if not channel_info or 'entries' not in channel_info:
                    logger.warning("No videos found or could not access videos with yt-dlp")
                    return []
                
                # Get videos list
                video_entries = channel_info['entries']
                logger.info(f"Found {len(video_entries)} videos in channel")
                
                # Process each video entry
                for i, entry in enumerate(video_entries):
                    try:
                        if not entry or 'id' not in entry:
                            continue
                            
                        logger.debug(f"Processing video {i+1}/{len(video_entries)}: {entry.get('title', 'Unknown')}")
                        
                        # Get more detailed info for this video
                        video_id = entry['id']
                        video_url = f"https://youtube.com/watch?v={video_id}"
                        
                        # Get detailed info with separate request for view count, duration etc.
                        try:
                            with YoutubeDL({'quiet': True}) as detail_ydl:
                                detail_info = detail_ydl.extract_info(video_url, download=False)
                                
                                # Create Video object with detailed info
                                video = Video(
                                    video_id=video_id,
                                    title=entry.get('title', "Untitled"),
                                    thumbnail_url=entry.get('thumbnails', [{}])[-1].get('url', '') if entry.get('thumbnails') else '',
                                    channel_title=channel_name,
                                    duration=detail_info.get('duration', 0),
                                    publish_date=detail_info.get('upload_date', ""),
                                    description=detail_info.get('description', ""),
                                    view_count=detail_info.get('view_count', 0)
                                )
                                
                                videos.append(video)
                                logger.debug(f"Successfully processed video: {video.title}")
                        except Exception as e:
                            # If detailed info fails, create with minimal info
                            logger.warning(f"Could not get detailed info for video {video_id}, using minimal info: {str(e)}")
                            video = Video(
                                video_id=video_id,
                                title=entry.get('title', "Untitled"),
                                thumbnail_url=entry.get('thumbnails', [{}])[-1].get('url', '') if entry.get('thumbnails') else '',
                                channel_title=channel_name,
                                duration=0,
                                publish_date="",
                                description="",
                                view_count=0
                            )
                            videos.append(video)
                            
                    except Exception as e:
                        logger.error(f"Error processing video entry: {str(e)}")
                        continue
                
            elapsed_time = time.time() - start_time
            logger.info(f"Successfully fetched {len(videos)} videos in {elapsed_time:.2f} seconds")
                    
        except Exception as e:
            logger.error(f"Error fetching channel videos: {str(e)}", exc_info=True)
        
        return videos

    @staticmethod
    def get_channel_playlists(channel_url: str) -> List[Playlist]:
        """
        Fetch playlists from a given YouTube channel.

        Args:
            channel_url: URL of the YouTube channel

        Returns:
            List[Playlist]: List of playlists from the channel
        """
        playlists = []
        logger.info(f"Fetching playlists from channel: {channel_url}")
        
        try:
            start_time = time.time()
            
            # Extract channel ID first
            channel_id = YouTubeAPI.extract_channel_id(channel_url)
            if not channel_id:
                logger.error("Could not extract channel ID for playlists")
                return []
            
            # First approach: Try using pytube to get playlists (simpler but might not work for all channels)
            try:
                logger.info("Attempting to fetch playlists using pytube...")
                channel = pytube.Channel(channel_url)
                channel_title = channel.channel_name
                
                # Get all playlist URLs (this is an undocumented feature in pytube)
                # If this fails, we'll fall back to yt-dlp
                if hasattr(channel, 'playlists'):
                    logger.info(f"Found playlists attribute in pytube Channel")
                    for playlist_url in channel.playlists:
                        try:
                            # Use pytube's Playlist
                            logger.debug(f"Processing playlist URL: {playlist_url}")
                            playlist_obj = pytube.Playlist(playlist_url)
                            playlist_id = playlist_url.split('list=')[1]
                            
                            # Create Playlist object
                            playlist = Playlist(
                                playlist_id=playlist_id,
                                title=playlist_obj.title,
                                thumbnail_url='',  # Pytube doesn't provide thumbnail URLs for playlists
                                channel_title=channel_title,
                                video_count=len(playlist_obj.video_urls),
                                description="",  # Pytube doesn't provide descriptions for playlists
                                last_updated=""  # Pytube doesn't provide last updated dates
                            )
                            
                            playlists.append(playlist)
                            logger.debug(f"Successfully processed playlist: {playlist.title} with {playlist.video_count} videos")
                        except Exception as e:
                            logger.debug(f"Error processing playlist with pytube: {str(e)}")
                            continue
                    
                    if playlists:
                        logger.info(f"Successfully fetched {len(playlists)} playlists using pytube")
                        return playlists
            except Exception as e:
                logger.debug(f"Could not fetch playlists using pytube: {str(e)}")
                # Fall back to yt-dlp method
                pass
                
            # Second approach: Use yt-dlp with a more resilient configuration
            logger.info(f"Fetching playlists for channel ID: {channel_id} using yt-dlp")
            channel_playlists_url = f"https://youtube.com/channel/{channel_id}/playlists"
            
            # Configure yt-dlp with better options for handling large responses
            ydl_opts = {
                'quiet': True,
                'extract_flat': True,
                'lazy_playlist': False,
                'ignoreerrors': True,  # Don't stop on errors
                'timeout': 30,         # Set a reasonable timeout
                'retries': 5,          # More retries
                'fragment_retries': 5, # More fragment retries
                'skip_unavailable_fragments': True,
                'no_color': True
            }
            
            with YoutubeDL(ydl_opts) as ydl:
                try:
                    channel_info = ydl.extract_info(channel_playlists_url, download=False)
                    
                    if not channel_info or 'entries' not in channel_info:
                        logger.warning("No playlists found or could not access playlists with yt-dlp")
                        return playlists  # Return whatever we have so far
                    
                    # Get channel title
                    channel_title = channel_info.get('channel', None) or channel_info.get('uploader', "Unknown Channel")
                    logger.info(f"Found playlists for channel: {channel_title}")
                    
                    # Process each playlist entry - don't try to get detailed info for each one
                    # to avoid overwhelming YouTube with requests
                    for i, entry in enumerate(channel_info['entries']):
                        try:
                            if entry and 'id' in entry and 'title' in entry:
                                logger.debug(f"Processing playlist {i+1}/{len(channel_info['entries'])}: {entry['title']}")
                                
                                # Build playlist with available info without making an additional request
                                video_count = entry.get('playlist_count', 0) or 0
                                
                                # Create Playlist object with minimal info
                                playlist = Playlist(
                                    playlist_id=entry['id'],
                                    title=entry['title'],
                                    thumbnail_url=entry.get('thumbnails', [{}])[-1].get('url', '') if entry.get('thumbnails') else '',
                                    channel_title=channel_title,
                                    video_count=video_count,
                                    description=entry.get('description', ""),
                                    last_updated=entry.get('modified_date', "")
                                )
                                
                                playlists.append(playlist)
                                logger.debug(f"Added playlist: {playlist.title}")
                                
                        except Exception as e:
                            logger.error(f"Error processing playlist entry: {str(e)}")
                            continue
                except Exception as e:
                    logger.error(f"Error extracting playlists with yt-dlp: {str(e)}")
            
            elapsed_time = time.time() - start_time
            logger.info(f"Successfully fetched {len(playlists)} playlists in {elapsed_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error fetching channel playlists: {str(e)}", exc_info=True)
            
        return playlists

    @staticmethod
    def get_playlist_videos(playlist_id: str) -> List[Video]:
        """
        Fetch videos from a specific YouTube playlist.

        Args:
            playlist_id: YouTube playlist ID

        Returns:
            List[Video]: List of videos in the playlist
        """
        videos = []
        logger.info(f"Fetching videos from playlist: {playlist_id}")
        
        try:
            start_time = time.time()
            playlist_url = f"https://youtube.com/playlist?list={playlist_id}"
            
            with YoutubeDL({'quiet': True, 'extract_flat': False}) as ydl:
                playlist_info = ydl.extract_info(playlist_url, download=False)
                
                if not playlist_info or 'entries' not in playlist_info:
                    logger.warning("No videos found in playlist or could not access playlist")
                    return []
                
                # Get channel title and playlist title
                channel_title = playlist_info.get('channel', None) or playlist_info.get('uploader', "Unknown Channel")
                playlist_title = playlist_info.get('title', "Unknown Playlist")
                logger.info(f"Found {len(playlist_info['entries'])} videos in playlist: {playlist_title}")
                
                # Process each video entry
                for i, entry in enumerate(playlist_info['entries']):
                    try:
                        if not entry:
                            continue
                            
                        logger.debug(f"Processing video {i+1}/{len(playlist_info['entries'])}: {entry.get('title', 'Unknown')}")
                        
                        # Create Video object
                        video = Video(
                            video_id=entry['id'],
                            title=entry['title'],
                            thumbnail_url=entry.get('thumbnails', [{}])[-1].get('url') if entry.get('thumbnails') else '',
                            channel_title=channel_title,
                            duration=entry.get('duration', 0),
                            publish_date=entry.get('upload_date', ""),
                            description=entry.get('description', ""),
                            view_count=entry.get('view_count', 0)
                        )
                        
                        videos.append(video)
                        logger.debug(f"Successfully processed video: {video.title}")
                        
                    except Exception as e:
                        logger.error(f"Error processing playlist video: {str(e)}")
                        continue
            
            elapsed_time = time.time() - start_time
            logger.info(f"Successfully fetched {len(videos)} videos from playlist in {elapsed_time:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error fetching playlist videos: {str(e)}", exc_info=True)
            
        return videos

    @staticmethod
    def get_video_info(video_id: str) -> Optional[Dict[str, Any]]:
        """
        Get detailed information about a specific video.

        Args:
            video_id: YouTube video ID

        Returns:
            Optional[Dict[str, Any]]: Video information or None if not found
        """
        logger.info(f"Getting detailed info for video: {video_id}")
        try:
            with YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(f"https://youtube.com/watch?v={video_id}", download=False)
                logger.debug(f"Successfully retrieved info for video {video_id}")
                return info
        except Exception as e:
            logger.error(f"Error getting video info for {video_id}: {str(e)}")
            return None

    @staticmethod
    def get_video_transcript(video_id: str) -> Optional[str]:
        """
        Get the transcript for a video if available.

        Args:
            video_id: YouTube video ID

        Returns:
            Optional[str]: Video transcript or None if not available
        """
        logger.info(f"Fetching transcript for video: {video_id}")
        try:
            with YoutubeDL({'quiet': True, 'writesubtitles': True, 'subtitleslangs': ['en']}) as ydl:
                info = ydl.extract_info(f"https://youtube.com/watch?v={video_id}", download=False)
                if info.get('requested_subtitles') and info['requested_subtitles'].get('en'):
                    logger.info(f"Transcript found for video {video_id}")
                    return info['requested_subtitles']['en']
                logger.warning(f"No transcript available for video {video_id}")
                return None
        except Exception as e:
            logger.error(f"Error getting transcript for {video_id}: {str(e)}")
            return None 