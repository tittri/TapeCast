"""
Metadata extraction and management for TapeCast

Handles:
- Basic metadata extraction from YouTube/local files
- Audio file tagging with mutagen
- Metadata persistence in JSON format
- Thumbnail processing
- (Future) AI enhancement with Whisper and Claude
"""

import json
import re
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict, field
from datetime import datetime
from PIL import Image
import mutagen
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.flac import FLAC
from mutagen.oggopus import OggOpus
from mutagen.wave import WAVE
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, COMM, APIC, TRCK
from .config import settings
from .exceptions import MetadataError
from .utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class Chapter:
    """Chapter marker in audio"""
    timestamp: str  # Format: "HH:MM:SS" or "MM:SS"
    title: str
    description: Optional[str] = None


@dataclass
class EpisodeMetadata:
    """Complete metadata for a podcast episode"""
    # Source metadata
    title: str
    description: str
    duration: float = 0.0
    upload_date: Optional[str] = None
    uploader: Optional[str] = None
    original_url: Optional[str] = None
    thumbnail_url: Optional[str] = None

    # Processing metadata
    profile_used: Optional[str] = None
    format: Optional[str] = None
    bitrate: Optional[str] = None
    loudness_lufs: Optional[float] = None
    file_size_bytes: Optional[int] = None
    processed_date: Optional[str] = None

    # Enhanced metadata (for AI enhancement later)
    enhanced_title: Optional[str] = None
    enhanced_description: Optional[str] = None
    summary: Optional[str] = None
    transcript: Optional[str] = None
    chapters: List[Chapter] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    language: Optional[str] = None

    # Podcast-specific metadata
    episode_number: Optional[int] = None
    season_number: Optional[int] = None
    podcast_title: Optional[str] = None

    # Flags
    ai_enriched: bool = False
    is_local_file: bool = False

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        # Convert chapters to dicts
        data['chapters'] = [asdict(ch) for ch in self.chapters]
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodeMetadata':
        """Create from dictionary"""
        # Convert chapter dicts to Chapter objects
        if 'chapters' in data:
            data['chapters'] = [Chapter(**ch) for ch in data['chapters']]
        return cls(**data)

    def save(self, path: Path) -> None:
        """Save metadata to JSON file"""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.debug(f"Saved metadata to {path}")

    @classmethod
    def load(cls, path: Path) -> 'EpisodeMetadata':
        """Load metadata from JSON file"""
        if not path.exists():
            raise MetadataError(f"Metadata file not found: {path}")

        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        return cls.from_dict(data)

    def get_display_title(self) -> str:
        """Get the best title for display"""
        return self.enhanced_title or self.title

    def get_display_description(self) -> str:
        """Get the best description for display"""
        return self.enhanced_description or self.description


class MetadataExtractor:
    """Extract and manage metadata for audio files"""

    def __init__(self):
        """Initialize metadata extractor"""
        self.thumbnail_cache = {}

    def extract_from_download(
        self,
        download_metadata: Dict[str, Any],
        audio_path: Path,
        playlist_index: Optional[int] = None,
    ) -> EpisodeMetadata:
        """
        Extract metadata from yt-dlp download info

        Args:
            download_metadata: Metadata dict from yt-dlp
            audio_path: Path to downloaded audio file
            playlist_index: Optional playlist index

        Returns:
            EpisodeMetadata object
        """
        # Clean title
        title = self._clean_title(download_metadata.get('title', 'Unknown'))

        # Extract episode/season from title if present
        episode_num, season_num = self._extract_episode_info(title)
        if playlist_index and not episode_num:
            episode_num = playlist_index

        # Build metadata object
        metadata = EpisodeMetadata(
            title=title,
            description=download_metadata.get('description', ''),
            duration=download_metadata.get('duration', 0),
            upload_date=self._format_date(download_metadata.get('upload_date', '')),
            uploader=download_metadata.get('uploader', download_metadata.get('channel', '')),
            original_url=download_metadata.get('webpage_url', download_metadata.get('original_url', '')),
            thumbnail_url=self._get_best_thumbnail(download_metadata.get('thumbnails', [])) or
                         download_metadata.get('thumbnail', ''),
            episode_number=episode_num,
            season_number=season_num,
            tags=download_metadata.get('tags', [])[:10],  # Limit tags
            is_local_file=download_metadata.get('is_local_file', False),
        )

        # Get file info
        if audio_path.exists():
            metadata.file_size_bytes = audio_path.stat().st_size

        return metadata

    def tag_audio_file(
        self,
        audio_path: Path,
        metadata: EpisodeMetadata,
        cover_art_path: Optional[Path] = None,
    ) -> None:
        """
        Write metadata tags to audio file

        Args:
            audio_path: Path to audio file
            metadata: Metadata to write
            cover_art_path: Optional path to cover art image
        """
        try:
            # Determine file format
            suffix = audio_path.suffix.lower()

            if suffix == '.mp3':
                self._tag_mp3(audio_path, metadata, cover_art_path)
            elif suffix == '.m4a':
                self._tag_m4a(audio_path, metadata, cover_art_path)
            elif suffix == '.flac':
                self._tag_flac(audio_path, metadata, cover_art_path)
            elif suffix == '.opus':
                self._tag_opus(audio_path, metadata, cover_art_path)
            elif suffix == '.wav':
                self._tag_wav(audio_path, metadata, cover_art_path)
            else:
                logger.warning(f"Unsupported format for tagging: {suffix}")

            logger.info(f"Tagged audio file: {audio_path.name}")

        except Exception as e:
            logger.error(f"Failed to tag audio file: {e}")
            # Don't raise - tagging is not critical

    def _tag_mp3(self, path: Path, metadata: EpisodeMetadata, cover_art: Optional[Path]) -> None:
        """Tag MP3 file using ID3"""
        try:
            audio = MP3(path)
        except:
            audio = mutagen.File(path, easy=False)
            audio.add_tags()

        # Clear existing tags
        audio.delete()
        audio.save()

        # Add ID3 tags
        audio["TIT2"] = TIT2(encoding=3, text=metadata.get_display_title())
        audio["TPE1"] = TPE1(encoding=3, text=metadata.uploader or "Unknown")
        audio["TALB"] = TALB(encoding=3, text=metadata.podcast_title or "TapeCast Podcast")

        if metadata.upload_date:
            year = metadata.upload_date[:4]
            audio["TDRC"] = TDRC(encoding=3, text=year)

        if metadata.episode_number:
            audio["TRCK"] = TRCK(encoding=3, text=str(metadata.episode_number))

        # Add comment with description
        if metadata.get_display_description():
            audio["COMM::eng"] = COMM(
                encoding=3,
                lang="eng",
                desc="Description",
                text=metadata.get_display_description()[:500]  # Limit length
            )

        # Add cover art
        if cover_art and cover_art.exists():
            with open(cover_art, 'rb') as f:
                audio["APIC"] = APIC(
                    encoding=3,
                    mime='image/jpeg',
                    type=3,  # Cover (front)
                    desc='Cover',
                    data=f.read()
                )

        audio.save()

    def _tag_m4a(self, path: Path, metadata: EpisodeMetadata, cover_art: Optional[Path]) -> None:
        """Tag M4A file"""
        audio = MP4(path)

        audio["\xa9nam"] = metadata.get_display_title()
        audio["\xa9ART"] = metadata.uploader or "Unknown"
        audio["\xa9alb"] = metadata.podcast_title or "TapeCast Podcast"
        audio["\xa9cmt"] = metadata.get_display_description()[:500]

        if metadata.upload_date:
            audio["\xa9day"] = metadata.upload_date[:4]

        if metadata.episode_number:
            audio["trkn"] = [(metadata.episode_number, 0)]

        # Add cover art
        if cover_art and cover_art.exists():
            with open(cover_art, 'rb') as f:
                audio["covr"] = [MP4Cover(f.read(), imageformat=MP4Cover.FORMAT_JPEG)]

        audio.save()

    def _tag_flac(self, path: Path, metadata: EpisodeMetadata, cover_art: Optional[Path]) -> None:
        """Tag FLAC file"""
        audio = FLAC(path)

        audio["title"] = metadata.get_display_title()
        audio["artist"] = metadata.uploader or "Unknown"
        audio["album"] = metadata.podcast_title or "TapeCast Podcast"
        audio["comment"] = metadata.get_display_description()[:500]

        if metadata.upload_date:
            audio["date"] = metadata.upload_date[:4]

        if metadata.episode_number:
            audio["tracknumber"] = str(metadata.episode_number)

        # Add cover art
        if cover_art and cover_art.exists():
            pic = mutagen.flac.Picture()
            pic.type = 3  # Cover (front)
            pic.mime = 'image/jpeg'
            pic.desc = 'Cover'
            with open(cover_art, 'rb') as f:
                pic.data = f.read()
            audio.add_picture(pic)

        audio.save()

    def _tag_opus(self, path: Path, metadata: EpisodeMetadata, cover_art: Optional[Path]) -> None:
        """Tag Opus file"""
        audio = OggOpus(path)

        audio["title"] = metadata.get_display_title()
        audio["artist"] = metadata.uploader or "Unknown"
        audio["album"] = metadata.podcast_title or "TapeCast Podcast"
        audio["comment"] = metadata.get_display_description()[:500]

        if metadata.upload_date:
            audio["date"] = metadata.upload_date[:4]

        if metadata.episode_number:
            audio["tracknumber"] = str(metadata.episode_number)

        audio.save()

    def _tag_wav(self, path: Path, metadata: EpisodeMetadata, cover_art: Optional[Path]) -> None:
        """Tag WAV file (limited support)"""
        try:
            audio = WAVE(path)
            # WAV has very limited tagging support
            # Try to add ID3 tags if possible
            if hasattr(audio, 'add_tags'):
                audio.add_tags()
                audio["TIT2"] = TIT2(encoding=3, text=metadata.get_display_title())
                audio["TPE1"] = TPE1(encoding=3, text=metadata.uploader or "Unknown")
                audio.save()
        except:
            logger.debug("WAV file does not support tagging")

    def download_thumbnail(
        self,
        url: str,
        output_path: Path,
        make_square: bool = True,
        size: int = 1400,
    ) -> Optional[Path]:
        """
        Download and process thumbnail image

        Args:
            url: Thumbnail URL
            output_path: Where to save the image
            make_square: Whether to crop to square for podcast use
            size: Target size for square image

        Returns:
            Path to saved image or None if failed
        """
        if not url:
            return None

        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download image
            logger.debug(f"Downloading thumbnail from {url}")
            urllib.request.urlretrieve(url, output_path)

            if make_square:
                # Process image to square
                square_path = output_path.with_name(f"{output_path.stem}_square.jpg")
                self._make_square_thumbnail(output_path, square_path, size)
                return square_path

            return output_path

        except Exception as e:
            logger.error(f"Failed to download thumbnail: {e}")
            return None

    def _make_square_thumbnail(
        self,
        input_path: Path,
        output_path: Path,
        size: int = 1400,
    ) -> None:
        """Create a square thumbnail for podcast use"""
        try:
            # Open and convert to RGB (in case it's RGBA)
            img = Image.open(input_path)
            if img.mode != 'RGB':
                img = img.convert('RGB')

            # Get dimensions
            width, height = img.size

            # Calculate crop box for center square
            if width > height:
                # Landscape - crop sides
                left = (width - height) // 2
                right = left + height
                top = 0
                bottom = height
            elif height > width:
                # Portrait - crop top/bottom
                top = (height - width) // 2
                bottom = top + width
                left = 0
                right = width
            else:
                # Already square
                left = top = 0
                right = width
                bottom = height

            # Crop to square
            img = img.crop((left, top, right, bottom))

            # Resize to target size
            img = img.resize((size, size), Image.Resampling.LANCZOS)

            # Save with good quality
            img.save(output_path, 'JPEG', quality=90, optimize=True)

            logger.debug(f"Created square thumbnail: {output_path}")

        except Exception as e:
            logger.error(f"Failed to create square thumbnail: {e}")
            # Fall back to copying original
            import shutil
            shutil.copy2(input_path, output_path)

    def _clean_title(self, title: str) -> str:
        """Clean up video title for podcast use"""
        if not title:
            return "Unknown"

        # Remove common YouTube suffixes
        patterns_to_remove = [
            r'\[.*?\]',  # Remove anything in square brackets
            r'\(Official.*?\)',  # Remove (Official Video), etc.
            r'\(HD\)',
            r'\(HQ\)',
            r'\(Remaster.*?\)',
            r'\(Audio\)',
            r'\(Lyric.*?\)',
            r'- YouTube$',
            r'^\d+\.\s*',  # Remove leading numbers like "01. "
        ]

        for pattern in patterns_to_remove:
            title = re.sub(pattern, '', title, flags=re.IGNORECASE)

        # Clean up extra spaces and trim
        title = ' '.join(title.split())
        title = title.strip(' -–—')

        return title or "Unknown"

    def _extract_episode_info(self, title: str) -> tuple[Optional[int], Optional[int]]:
        """Extract episode and season numbers from title"""
        episode_num = None
        season_num = None

        # Common patterns
        patterns = [
            r'S(\d+)E(\d+)',  # S01E02
            r'Season\s*(\d+).*?Episode\s*(\d+)',  # Season 1 Episode 2
            r'Ep\.?\s*(\d+)',  # Ep. 12 or Ep 12
            r'Episode\s*(\d+)',  # Episode 12
            r'#(\d+)',  # #12
            r'^\d+\.\s',  # 12. at start
        ]

        # Try season + episode patterns
        for pattern in patterns[:2]:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                if len(match.groups()) == 2:
                    season_num = int(match.group(1))
                    episode_num = int(match.group(2))
                else:
                    episode_num = int(match.group(1))
                break

        # Try episode-only patterns
        if not episode_num:
            for pattern in patterns[2:]:
                match = re.search(pattern, title, re.IGNORECASE)
                if match:
                    episode_num = int(match.group(1))
                    break

        return episode_num, season_num

    def _format_date(self, date_str: str) -> Optional[str]:
        """Format date string to ISO format"""
        if not date_str:
            return None

        # yt-dlp usually gives YYYYMMDD
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        # Already formatted
        if '-' in date_str:
            return date_str

        return None

    def _get_best_thumbnail(self, thumbnails: List[Dict[str, Any]]) -> Optional[str]:
        """Get the best quality thumbnail URL from list"""
        if not thumbnails:
            return None

        # Sort by width/height if available
        sorted_thumbs = sorted(
            thumbnails,
            key=lambda t: (t.get('width', 0) * t.get('height', 0)),
            reverse=True
        )

        # Return highest res
        if sorted_thumbs:
            return sorted_thumbs[0].get('url')

        return None