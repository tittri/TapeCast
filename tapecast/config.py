"""
TapeCast configuration management using Pydantic
"""

import os
from pathlib import Path
from typing import Optional, Literal
from pydantic import Field, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """TapeCast configuration settings with environment variable support"""

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=False,
        extra='ignore'
    )

    # API Keys
    anthropic_api_key: Optional[str] = Field(None, env="ANTHROPIC_API_KEY")
    google_client_id: Optional[str] = Field(None, env="GOOGLE_CLIENT_ID")
    google_client_secret: Optional[str] = Field(None, env="GOOGLE_CLIENT_SECRET")

    # Paths
    output_dir: Path = Field(Path("./output"), env="TAPECAST_OUTPUT_DIR")
    downloads_dir: Optional[Path] = Field(None, env="TAPECAST_DOWNLOADS_DIR")
    processed_dir: Optional[Path] = Field(None, env="TAPECAST_PROCESSED_DIR")
    metadata_dir: Optional[Path] = Field(None, env="TAPECAST_METADATA_DIR")
    thumbnails_dir: Optional[Path] = Field(None, env="TAPECAST_THUMBNAILS_DIR")
    transcripts_dir: Optional[Path] = Field(None, env="TAPECAST_TRANSCRIPTS_DIR")

    # FFmpeg Configuration
    ffmpeg_path: str = Field("ffmpeg", env="FFMPEG_PATH")
    ffprobe_path: str = Field("ffprobe", env="FFPROBE_PATH")

    # Audio Processing Defaults
    default_format: Literal["mp3", "flac", "wav", "opus", "m4a"] = Field(
        "mp3", env="TAPECAST_DEFAULT_FORMAT"
    )
    default_profile: Literal["auto", "cassette", "vhs", "phone", "clean", "none"] = Field(
        "auto", env="TAPECAST_DEFAULT_PROFILE"
    )
    default_bitrate: str = Field("192k", env="TAPECAST_DEFAULT_BITRATE")
    loudness_lufs: float = Field(-16.0, env="TAPECAST_LOUDNESS")
    sample_rate: int = Field(44100, env="TAPECAST_SAMPLE_RATE")

    # Whisper Configuration
    whisper_model: Literal["tiny", "base", "small", "medium", "large"] = Field(
        "small", env="WHISPER_MODEL"
    )
    whisper_device: Literal["cpu", "cuda"] = Field("cpu", env="WHISPER_DEVICE")

    # Processing Configuration
    max_workers: int = Field(4, env="TAPECAST_MAX_WORKERS", ge=1, le=32)
    chunk_size: int = Field(8192, env="TAPECAST_CHUNK_SIZE", ge=1024)
    skip_existing: bool = Field(True, env="TAPECAST_SKIP_EXISTING")
    force_overwrite: bool = Field(False, env="TAPECAST_FORCE_OVERWRITE")

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", env="TAPECAST_LOG_LEVEL"
    )

    # YouTube Publishing
    youtube_visibility: Literal["public", "unlisted", "private"] = Field(
        "unlisted", env="YOUTUBE_VISIBILITY"
    )

    # Removed the problematic validator - we'll handle defaults in __init__

    def __init__(self, **values):
        super().__init__(**values)
        # Set default subdirectories after initialization
        if self.downloads_dir is None:
            self.downloads_dir = self.output_dir / "downloads"
        if self.processed_dir is None:
            self.processed_dir = self.output_dir / "processed"
        if self.metadata_dir is None:
            self.metadata_dir = self.output_dir / "metadata"
        if self.thumbnails_dir is None:
            self.thumbnails_dir = self.output_dir / "thumbnails"
        if self.transcripts_dir is None:
            self.transcripts_dir = self.output_dir / "transcripts"

    def setup_directories(self) -> None:
        """Create all necessary directories"""
        directories = [
            self.output_dir,
            self.downloads_dir,
            self.processed_dir,
            self.metadata_dir,
            self.thumbnails_dir,
            self.transcripts_dir,
        ]

        for directory in directories:
            if directory:
                directory.mkdir(parents=True, exist_ok=True)

    def validate_ffmpeg(self) -> bool:
        """Check if FFmpeg is available"""
        import shutil
        return shutil.which(self.ffmpeg_path) is not None

    def validate_api_keys(self, require_ai: bool = False) -> tuple[bool, list[str]]:
        """
        Validate API keys are present
        Returns: (all_valid, list_of_missing_keys)
        """
        missing = []

        if require_ai and not self.anthropic_api_key:
            missing.append("ANTHROPIC_API_KEY")

        return len(missing) == 0, missing

    def get_output_path(self, filename: str, subdir: str = "processed", extension: str = None) -> Path:
        """
        Generate an output path for a file

        Args:
            filename: Base filename (without extension)
            subdir: Subdirectory under output_dir
            extension: File extension (without dot)

        Returns:
            Full path to the output file
        """
        base_dir = getattr(self, f"{subdir}_dir", self.output_dir / subdir)
        if extension:
            filename = f"{filename}.{extension}"
        return base_dir / filename

    def to_dict(self) -> dict:
        """Convert settings to dictionary (excluding sensitive values)"""
        data = self.model_dump()
        # Mask sensitive values
        if data.get("anthropic_api_key"):
            data["anthropic_api_key"] = "***" + data["anthropic_api_key"][-4:]
        if data.get("google_client_secret"):
            data["google_client_secret"] = "***"
        return data


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get the global settings instance"""
    return settings


def reload_settings() -> Settings:
    """Reload settings from environment"""
    global settings
    settings = Settings()
    return settings