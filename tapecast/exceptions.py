"""
TapeCast custom exception hierarchy
"""


class TapeCastError(Exception):
    """Base exception for all TapeCast errors"""
    pass


class DownloadError(TapeCastError):
    """Error during YouTube download"""
    pass


class ProcessingError(TapeCastError):
    """Error during audio processing"""
    pass


class MetadataError(TapeCastError):
    """Error during metadata extraction or enrichment"""
    pass


class PublishingError(TapeCastError):
    """Error during publishing to YouTube or podcast RSS"""
    pass


class ProfileError(TapeCastError):
    """Error with audio profile configuration or selection"""
    pass


class FFmpegError(ProcessingError):
    """Error from FFmpeg subprocess"""
    pass


class ConfigurationError(TapeCastError):
    """Error with configuration or environment setup"""
    pass


class AuthenticationError(TapeCastError):
    """Error with API authentication (YouTube, Anthropic, etc.)"""
    pass