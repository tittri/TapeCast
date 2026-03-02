"""
TapeCast - YouTube-to-Podcast Audio Enhancement CLI

Transform YouTube videos into podcast episodes with retro audio profiles.
"""

__version__ = "0.1.0"
__author__ = "Your Name"
__email__ = "your.email@example.com"

from .exceptions import (
    TapeCastError,
    DownloadError,
    ProcessingError,
    MetadataError,
    PublishingError,
    ProfileError,
    FFmpegError,
)

__all__ = [
    "TapeCastError",
    "DownloadError",
    "ProcessingError",
    "MetadataError",
    "PublishingError",
    "ProfileError",
    "FFmpegError",
]