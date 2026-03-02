"""
Batch loader for processing URLs from text files

Loads YouTube URLs from text files with support for comments and validation.
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional
from .exceptions import TapeCastError
from .utils.logger import get_logger


logger = get_logger(__name__)


class BatchLoader:
    """Load and validate URLs from text files"""

    @staticmethod
    def load_urls_from_file(
        file_path: Path,
        skip_invalid: bool = False,
        validate_youtube: bool = True
    ) -> Tuple[List[str], List[str]]:
        """
        Load URLs from a text file

        Supports:
        - Comments (lines starting with #)
        - Empty lines (ignored)
        - YouTube video URLs
        - YouTube playlist URLs
        - Local file paths

        Args:
            file_path: Path to text file containing URLs
            skip_invalid: If True, skip invalid URLs; if False, fail on first invalid
            validate_youtube: If True, validate YouTube URL format

        Returns:
            Tuple of (valid_urls, skipped_lines)

        Raises:
            TapeCastError: If file not found or invalid URLs when skip_invalid=False
        """
        if not file_path.exists():
            raise TapeCastError(f"File not found: {file_path}")

        if not file_path.is_file():
            raise TapeCastError(f"Not a file: {file_path}")

        valid_urls = []
        skipped_lines = []
        line_count = 0
        comment_count = 0
        empty_count = 0

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line_count += 1
                    original_line = line.rstrip('\n\r')
                    line = line.strip()

                    # Skip empty lines
                    if not line:
                        empty_count += 1
                        continue

                    # Skip comments
                    if line.startswith('#'):
                        comment_count += 1
                        logger.debug(f"Line {line_num}: Skipping comment")
                        continue

                    # Validate and add URL
                    if BatchLoader.is_valid_url(line, validate_youtube):
                        valid_urls.append(line)
                        logger.debug(f"Line {line_num}: Added URL {line[:50]}...")
                    else:
                        error_msg = f"Line {line_num}: {original_line}"
                        skipped_lines.append(error_msg)
                        logger.warning(f"Line {line_num}: Invalid URL format: {line[:50]}...")

                        if not skip_invalid:
                            raise TapeCastError(
                                f"Invalid URL at line {line_num}: {line[:100]}\n"
                                f"Use --skip-invalid to continue with valid URLs only"
                            )

        except UnicodeDecodeError as e:
            raise TapeCastError(f"Error reading file (invalid encoding): {e}")
        except IOError as e:
            raise TapeCastError(f"Error reading file: {e}")

        # Log statistics
        logger.info(
            f"Loaded {len(valid_urls)} URLs from {file_path.name} "
            f"({line_count} lines, {comment_count} comments, {empty_count} empty)"
        )

        return valid_urls, skipped_lines

    @staticmethod
    def is_valid_url(url: str, validate_youtube: bool = True) -> bool:
        """
        Validate if string is a valid YouTube URL or local file

        Args:
            url: URL string to validate
            validate_youtube: If True, validate YouTube URL format strictly

        Returns:
            True if valid YouTube URL or existing local file
        """
        if not url or not isinstance(url, str):
            return False

        # Remove leading/trailing whitespace
        url = url.strip()

        # Check for YouTube URL patterns
        youtube_patterns = [
            # Standard YouTube video URLs
            r'^https?://(www\.)?youtube\.com/watch\?v=[\w\-]+',
            r'^https?://(www\.)?youtube\.com/watch\?.*v=[\w\-]+',
            # YouTube short URLs
            r'^https?://youtu\.be/[\w\-]+',
            # YouTube playlist URLs
            r'^https?://(www\.)?youtube\.com/playlist\?list=[\w\-]+',
            r'^https?://(www\.)?youtube\.com/watch\?.*list=[\w\-]+',
            # YouTube channel URLs
            r'^https?://(www\.)?youtube\.com/c/[\w\-]+',
            r'^https?://(www\.)?youtube\.com/channel/[\w\-]+',
            r'^https?://(www\.)?youtube\.com/user/[\w\-]+',
            r'^https?://(www\.)?youtube\.com/@[\w\-]+',
        ]

        # Relaxed patterns (without protocol)
        relaxed_patterns = [
            r'^(www\.)?youtube\.com/watch\?v=[\w\-]+',
            r'^(www\.)?youtube\.com/playlist\?list=[\w\-]+',
            r'^youtu\.be/[\w\-]+',
        ]

        # Check YouTube patterns
        if validate_youtube:
            for pattern in youtube_patterns:
                if re.match(pattern, url, re.IGNORECASE):
                    return True

            # Try relaxed patterns and auto-fix
            for pattern in relaxed_patterns:
                if re.match(pattern, url, re.IGNORECASE):
                    logger.debug(f"URL missing protocol, will be auto-fixed: {url}")
                    return True
        else:
            # Very relaxed validation - just check if it looks like a URL
            if 'youtube.com' in url.lower() or 'youtu.be' in url.lower():
                return True

        # Check if it's a valid local file
        try:
            path = Path(url).expanduser()
            if path.exists() and path.is_file():
                # Check for supported audio/video extensions
                supported_extensions = [
                    '.mp3', '.mp4', '.m4a', '.wav', '.flac', '.ogg',
                    '.webm', '.mkv', '.avi', '.mov', '.opus'
                ]
                if path.suffix.lower() in supported_extensions:
                    logger.debug(f"Valid local file: {path}")
                    return True
        except (ValueError, OSError):
            # Invalid path, continue checking
            pass

        return False

    @staticmethod
    def normalize_url(url: str) -> str:
        """
        Normalize URL by adding missing protocol if needed

        Args:
            url: URL string to normalize

        Returns:
            Normalized URL with protocol
        """
        url = url.strip()

        # If no protocol, add https://
        if not url.startswith(('http://', 'https://')):
            # Check if it looks like a YouTube URL
            if 'youtube.com' in url or 'youtu.be' in url:
                url = 'https://' + url

        return url

    @staticmethod
    def deduplicate_urls(urls: List[str]) -> Tuple[List[str], int]:
        """
        Remove duplicate URLs from list

        Args:
            urls: List of URLs

        Returns:
            Tuple of (unique_urls, duplicate_count)
        """
        seen = set()
        unique = []
        duplicates = 0

        for url in urls:
            normalized = BatchLoader.normalize_url(url)
            if normalized not in seen:
                seen.add(normalized)
                unique.append(url)
            else:
                duplicates += 1
                logger.debug(f"Skipping duplicate URL: {url[:50]}...")

        if duplicates > 0:
            logger.info(f"Removed {duplicates} duplicate URL(s)")

        return unique, duplicates

    @staticmethod
    def validate_batch(
        urls: List[str],
        max_urls: Optional[int] = None
    ) -> Tuple[List[str], List[str]]:
        """
        Validate a batch of URLs

        Args:
            urls: List of URLs to validate
            max_urls: Maximum number of URLs to accept (None for unlimited)

        Returns:
            Tuple of (valid_urls, invalid_urls)
        """
        valid = []
        invalid = []

        for url in urls:
            if BatchLoader.is_valid_url(url):
                valid.append(BatchLoader.normalize_url(url))
            else:
                invalid.append(url)

        # Apply limit if specified
        if max_urls and len(valid) > max_urls:
            logger.warning(f"Limiting to first {max_urls} URLs (found {len(valid)})")
            valid = valid[:max_urls]

        return valid, invalid

    @staticmethod
    def save_urls_to_file(urls: List[str], file_path: Path) -> None:
        """
        Save URLs to a text file (useful for creating templates)

        Args:
            urls: List of URLs to save
            file_path: Path to save file

        Raises:
            TapeCastError: If unable to write file
        """
        try:
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write("# TapeCast URL Batch File\n")
                f.write(f"# Generated: {Path.ctime(Path.cwd())}\n")
                f.write("# Add YouTube URLs below (one per line)\n")
                f.write("# Lines starting with # are comments\n\n")

                for url in urls:
                    f.write(f"{url}\n")

            logger.info(f"Saved {len(urls)} URLs to {file_path}")

        except IOError as e:
            raise TapeCastError(f"Error writing file: {e}")