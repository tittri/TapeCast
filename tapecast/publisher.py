"""
RSS feed generation and podcast publishing for TapeCast

Generates iTunes-compatible podcast RSS feeds from processed audio files.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin

from feedgen.feed import FeedGenerator
from mutagen import File as MutagenFile

from .config import settings
from .metadata import EpisodeMetadata
from .utils.logger import get_logger


logger = get_logger(__name__)


class PodcastFeed:
    """
    Generates and manages podcast RSS feeds

    Creates iTunes-compatible RSS 2.0 feeds with support for:
    - Episode management
    - Cover art
    - iTunes podcast categories
    - Multiple output formats
    """

    def __init__(
        self,
        title: str,
        description: str,
        author: str,
        base_url: str,
        language: str = "en-US",
        category: str = "Technology",
        explicit: bool = False,
        email: Optional[str] = None,
        website: Optional[str] = None,
        cover_image: Optional[str] = None,
    ):
        """
        Initialize podcast feed

        Args:
            title: Podcast title
            description: Podcast description
            author: Podcast author/owner
            base_url: Base URL where files will be hosted
            language: Podcast language (default: en-US)
            category: iTunes category (default: Technology)
            explicit: Whether podcast contains explicit content
            email: Contact email
            website: Podcast website
            cover_image: URL to podcast cover image
        """
        self.title = title
        self.description = description
        self.author = author
        self.base_url = base_url.rstrip('/')
        self.language = language
        self.category = category
        self.explicit = explicit
        self.email = email
        self.website = website
        self.cover_image = cover_image

        # Initialize feed generator
        self.feed = FeedGenerator()
        self._setup_feed()

    def _setup_feed(self) -> None:
        """Setup basic feed information"""
        # Basic feed info
        self.feed.title(self.title)
        self.feed.description(self.description)
        self.feed.author({'name': self.author, 'email': self.email or ''})
        self.feed.language(self.language)

        # Links
        feed_url = f"{self.base_url}/feed.xml"
        self.feed.id(feed_url)
        self.feed.link(href=feed_url, rel='self')

        if self.website:
            self.feed.link(href=self.website, rel='alternate')

        # Podcast extension
        self.feed.load_extension('podcast')
        self.feed.podcast.itunes_author(self.author)
        self.feed.podcast.itunes_summary(self.description)
        self.feed.podcast.itunes_category(self.category)
        self.feed.podcast.itunes_explicit('yes' if self.explicit else 'no')

        if self.email:
            self.feed.podcast.itunes_owner(name=self.author, email=self.email)

        if self.cover_image:
            self.feed.podcast.itunes_image(self.cover_image)
            self.feed.image(self.cover_image)

        # Generator
        self.feed.generator('TapeCast', uri='https://github.com/yourusername/tapecast')

    def add_episode(
        self,
        audio_file: Path,
        title: Optional[str] = None,
        description: Optional[str] = None,
        metadata_file: Optional[Path] = None,
        episode_number: Optional[int] = None,
        season_number: Optional[int] = None,
        published: Optional[datetime] = None,
    ) -> None:
        """
        Add an episode to the feed

        Args:
            audio_file: Path to audio file
            title: Episode title (uses filename if not provided)
            description: Episode description
            metadata_file: Path to metadata JSON file
            episode_number: Episode number
            season_number: Season number
            published: Publication date (uses file modified time if not provided)
        """
        if not audio_file.exists():
            logger.warning(f"Audio file not found: {audio_file}")
            return

        # Load metadata from file if provided
        episode_metadata = None
        if metadata_file and metadata_file.exists():
            try:
                episode_metadata = EpisodeMetadata.load(metadata_file)
                if not title:
                    title = episode_metadata.title
                if not description:
                    description = episode_metadata.description
            except Exception as e:
                logger.warning(f"Failed to load metadata from {metadata_file}: {e}")

        # Get audio file info
        audio_info = self._get_audio_info(audio_file)

        # Generate episode title
        if not title:
            title = audio_file.stem.replace('_tapecasted', '').replace('_', ' ')

        if episode_number:
            title = f"Episode {episode_number}: {title}"

        # Generate description
        if not description:
            description = f"Episode: {title}"
            if episode_metadata and episode_metadata.description:
                description = episode_metadata.description[:500]  # iTunes limit

        # Publication date
        if not published:
            published = datetime.fromtimestamp(audio_file.stat().st_mtime, tz=timezone.utc)

        # Create feed entry
        entry = self.feed.add_entry()
        entry.id(f"{self.base_url}/episodes/{audio_file.name}")
        entry.title(title)
        entry.description(description)
        entry.published(published)

        # Episode link
        episode_url = f"{self.base_url}/episodes/{audio_file.name}"
        entry.link(href=episode_url)

        # Enclosure (audio file)
        entry.enclosure(
            url=episode_url,
            length=str(audio_file.stat().st_size),
            type=self._get_mime_type(audio_file)
        )

        # iTunes extensions
        entry.podcast.itunes_author(self.author)
        entry.podcast.itunes_summary(description)
        entry.podcast.itunes_duration(audio_info.get('duration_str', '00:00'))

        if episode_number:
            entry.podcast.itunes_episode(episode_number)
        if season_number:
            entry.podcast.itunes_season(season_number)

        # Episode image (from metadata or default)
        if episode_metadata and episode_metadata.thumbnail_url:
            entry.podcast.itunes_image(episode_metadata.thumbnail_url)
        elif self.cover_image:
            entry.podcast.itunes_image(self.cover_image)

        logger.info(f"Added episode to feed: {title}")

    def add_episodes_from_directory(
        self,
        directory: Path,
        pattern: str = "*.mp3",
        sort_by: str = "name",
        reverse: bool = False,
        limit: Optional[int] = None,
    ) -> int:
        """
        Add multiple episodes from a directory

        Args:
            directory: Directory containing audio files
            pattern: File pattern to match (default: *.mp3)
            sort_by: Sort by 'name', 'date', or 'size'
            reverse: Reverse sort order
            limit: Maximum number of episodes to add

        Returns:
            Number of episodes added
        """
        if not directory.exists():
            logger.error(f"Directory not found: {directory}")
            return 0

        # Find audio files
        audio_files = list(directory.glob(pattern))

        if not audio_files:
            logger.warning(f"No files matching {pattern} in {directory}")
            return 0

        # Sort files
        if sort_by == "date":
            audio_files.sort(key=lambda f: f.stat().st_mtime, reverse=reverse)
        elif sort_by == "size":
            audio_files.sort(key=lambda f: f.stat().st_size, reverse=reverse)
        else:  # name
            audio_files.sort(key=lambda f: f.name, reverse=reverse)

        # Apply limit
        if limit:
            audio_files = audio_files[:limit]

        # Add episodes
        for idx, audio_file in enumerate(audio_files, 1):
            # Look for corresponding metadata file
            metadata_file = directory.parent / "metadata" / f"{audio_file.stem}.json"

            self.add_episode(
                audio_file=audio_file,
                metadata_file=metadata_file if metadata_file.exists() else None,
                episode_number=idx,
            )

        logger.info(f"Added {len(audio_files)} episodes from {directory}")
        return len(audio_files)

    def save(self, output_path: Path) -> None:
        """
        Save RSS feed to file

        Args:
            output_path: Path to save RSS feed
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.feed.rss_file(str(output_path))
            logger.info(f"Saved RSS feed to {output_path}")
        except Exception as e:
            logger.error(f"Failed to save RSS feed: {e}")
            raise

    def serve(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """
        Serve the RSS feed via HTTP (for testing)

        Args:
            host: Host to bind to
            port: Port to bind to
        """
        import http.server
        import socketserver
        from tempfile import NamedTemporaryFile

        # Save feed to temp file
        with NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            self.feed.rss_file(f.name)
            feed_path = Path(f.name)

        class FeedHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                if self.path == '/feed.xml':
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/rss+xml')
                    self.end_headers()
                    self.wfile.write(feed_path.read_bytes())
                else:
                    super().do_GET()

        try:
            with socketserver.TCPServer((host, port), FeedHandler) as httpd:
                logger.info(f"Serving RSS feed at http://{host}:{port}/feed.xml")
                logger.info("Press Ctrl+C to stop")
                httpd.serve_forever()
        finally:
            feed_path.unlink()

    def _get_audio_info(self, audio_file: Path) -> Dict[str, Any]:
        """Get audio file information using mutagen"""
        info = {}
        try:
            audio = MutagenFile(str(audio_file))
            if audio and audio.info:
                duration = int(audio.info.length)
                hours = duration // 3600
                minutes = (duration % 3600) // 60
                seconds = duration % 60

                if hours > 0:
                    info['duration_str'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                else:
                    info['duration_str'] = f"{minutes:02d}:{seconds:02d}"

                info['duration'] = duration
                info['bitrate'] = getattr(audio.info, 'bitrate', 0)
                info['sample_rate'] = getattr(audio.info, 'sample_rate', 0)
        except Exception as e:
            logger.warning(f"Failed to get audio info for {audio_file}: {e}")
            info['duration_str'] = "00:00"

        return info

    def _get_mime_type(self, audio_file: Path) -> str:
        """Get MIME type for audio file"""
        suffix_map = {
            '.mp3': 'audio/mpeg',
            '.m4a': 'audio/mp4',
            '.mp4': 'audio/mp4',
            '.opus': 'audio/opus',
            '.ogg': 'audio/ogg',
            '.flac': 'audio/flac',
            '.wav': 'audio/wav',
        }
        return suffix_map.get(audio_file.suffix.lower(), 'audio/mpeg')


class FeedConfig:
    """Configuration for podcast feed"""

    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize feed configuration

        Args:
            config_file: Path to configuration JSON file
        """
        if config_file is None:
            config_file = Path.home() / ".tapecast" / "feed_config.json"

        self.config_file = config_file
        self.config = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from file"""
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load feed config: {e}")

        # Default configuration
        return {
            'title': 'My TapeCast Podcast',
            'description': 'A podcast created with TapeCast',
            'author': 'TapeCast User',
            'base_url': 'http://localhost:8000',
            'language': 'en-US',
            'category': 'Technology',
            'explicit': False,
        }

    def save(self) -> None:
        """Save configuration to file"""
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Saved feed config to {self.config_file}")
        except Exception as e:
            logger.error(f"Failed to save feed config: {e}")

    def create_feed(self) -> PodcastFeed:
        """Create PodcastFeed instance from configuration"""
        return PodcastFeed(**self.config)