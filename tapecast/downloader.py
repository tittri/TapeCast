"""
YouTube downloader module for TapeCast

Uses yt-dlp to download audio from YouTube videos and playlists
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import yt_dlp
from .config import settings
from .exceptions import DownloadError
from .utils.logger import get_logger, console
from .utils.progress import DownloadProgressCallback
from rich.progress import Progress


logger = get_logger(__name__)


@dataclass
class DownloadResult:
    """Result from a download operation"""
    file_path: Path
    metadata: Dict[str, Any]
    source_url: str
    playlist_index: Optional[int] = None
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None


class YouTubeDownloader:
    """
    Download audio from YouTube videos and playlists using yt-dlp
    """

    def __init__(self, output_dir: Optional[Path] = None):
        """
        Initialize downloader

        Args:
            output_dir: Directory for downloaded files
        """
        self.output_dir = output_dir or settings.downloads_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def download(
        self,
        url: str,
        progress_bar: Optional[Progress] = None,
        task_id: Optional[int] = None,
        keep_original: bool = False,
        force: bool = False,
    ) -> List[DownloadResult]:
        """
        Download audio from YouTube URL (single video or playlist)

        Args:
            url: YouTube video or playlist URL, or local file path
            progress_bar: Optional Rich progress bar
            task_id: Optional task ID for progress bar
            keep_original: Keep downloaded file in original format
            force: Force re-download even if file exists

        Returns:
            List of DownloadResult objects
        """
        # Check if input is a local file
        local_path = Path(url)
        if local_path.exists() and local_path.is_file():
            logger.info(f"Processing local file: {local_path}")
            return [self._process_local_file(local_path)]

        # Validate URL
        if not self._is_valid_youtube_url(url):
            raise DownloadError(f"Invalid YouTube URL: {url}")

        # Detect if it's a playlist
        is_playlist = self._is_playlist_url(url)

        if is_playlist:
            logger.info(f"Downloading playlist from: {url}")
            return self._download_playlist(url, progress_bar, task_id, keep_original, force)
        else:
            logger.info(f"Downloading single video from: {url}")
            result = self._download_single(url, progress_bar, task_id, keep_original, force)
            return [result]

    def _download_single(
        self,
        url: str,
        progress_bar: Optional[Progress] = None,
        task_id: Optional[int] = None,
        keep_original: bool = False,
        force: bool = False,
    ) -> DownloadResult:
        """Download a single video"""
        try:
            # Configure yt-dlp options
            ydl_opts = self._get_ydl_options(
                playlist_index=None,
                progress_bar=progress_bar,
                task_id=task_id,
                keep_original=keep_original,
                force=force
            )

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first to check if file exists
                info = ydl.extract_info(url, download=False)

                # Check if file already exists
                output_path = self._get_output_path(info, playlist_index=None)
                if output_path.exists() and not force:
                    logger.info(f"File already exists, skipping: {output_path}")
                    return DownloadResult(
                        file_path=output_path,
                        metadata=self._extract_metadata(info),
                        source_url=url,
                        playlist_index=None,
                    )

                # Download the file
                info = ydl.extract_info(url, download=True)

                # Get the actual output path - yt-dlp might have sanitized the filename
                expected_path = self._get_output_path(info, playlist_index=None)

                # Find the actual file created by yt-dlp
                # Due to restrictfilenames, the actual file may have underscores
                if not expected_path.exists():
                    # Look for files with similar name pattern
                    pattern = f"*{info.get('id', '')}*.wav"
                    matching_files = list(self.output_dir.glob(pattern))
                    if matching_files:
                        output_path = matching_files[0]
                        logger.debug(f"Found actual file by ID: {output_path}")
                    else:
                        # Try with sanitized title
                        sanitized_title = self._sanitize_filename(info.get('title', 'Unknown'))
                        pattern = f"*{sanitized_title.replace(' ', '_')}*.wav"
                        matching_files = list(self.output_dir.glob(pattern))
                        if matching_files:
                            output_path = matching_files[0]
                            logger.debug(f"Found actual file by title: {output_path}")
                        else:
                            # Last resort: find any new WAV file
                            wav_files = list(self.output_dir.glob("*.wav"))
                            if wav_files:
                                # Get the most recently created file
                                output_path = max(wav_files, key=lambda p: p.stat().st_mtime)
                                logger.debug(f"Found actual file by newest: {output_path}")
                            else:
                                output_path = expected_path
                else:
                    output_path = expected_path

                return DownloadResult(
                    file_path=output_path,
                    metadata=self._extract_metadata(info),
                    source_url=url,
                    playlist_index=None,
                )

        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            return DownloadResult(
                file_path=Path(),
                metadata={},
                source_url=url,
                error=str(e)
            )

    def _download_playlist(
        self,
        url: str,
        progress_bar: Optional[Progress] = None,
        task_id: Optional[int] = None,
        keep_original: bool = False,
        force: bool = False,
    ) -> List[DownloadResult]:
        """Download all videos from a playlist"""
        results = []

        try:
            # First, get playlist info
            ydl_opts = self._get_ydl_options(
                playlist_index=None,
                progress_bar=None,
                task_id=None,
                keep_original=keep_original,
                force=force
            )
            ydl_opts['extract_flat'] = True  # Just get metadata

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                playlist_info = ydl.extract_info(url, download=False)

            if 'entries' not in playlist_info:
                raise DownloadError("No videos found in playlist")

            total_videos = len(playlist_info['entries'])
            playlist_title = playlist_info.get('title', 'Unknown Playlist')

            console.print(f"[cyan]Found {total_videos} videos in playlist: {playlist_title}[/cyan]")

            # Download each video
            for idx, entry in enumerate(playlist_info['entries'], 1):
                if entry is None:
                    logger.warning(f"Skipping deleted/private video at index {idx}")
                    results.append(DownloadResult(
                        file_path=Path(),
                        metadata={},
                        source_url=url,
                        playlist_index=idx,
                        error="Video is deleted or private"
                    ))
                    continue

                video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                video_title = entry.get('title', f'Video {idx}')

                console.print(f"[dim]Downloading {idx}/{total_videos}: {video_title}[/dim]")

                # Download the video
                result = self._download_single_from_playlist(
                    video_url,
                    playlist_index=idx,
                    total_videos=total_videos,
                    progress_bar=progress_bar,
                    task_id=task_id,
                    keep_original=keep_original,
                    force=force
                )

                results.append(result)

            # Summary
            successful = sum(1 for r in results if r.is_success)
            console.print(f"\n[green]Downloaded {successful}/{total_videos} videos successfully[/green]")

            if successful < total_videos:
                failed = [r for r in results if not r.is_success]
                console.print(f"[yellow]Failed downloads ({len(failed)}):[/yellow]")
                for r in failed:
                    console.print(f"  - Index {r.playlist_index}: {r.error}")

            return results

        except Exception as e:
            logger.error(f"Playlist download failed: {e}")
            raise DownloadError(f"Failed to download playlist: {e}")

    def _download_single_from_playlist(
        self,
        url: str,
        playlist_index: int,
        total_videos: int,
        progress_bar: Optional[Progress] = None,
        task_id: Optional[int] = None,
        keep_original: bool = False,
        force: bool = False,
    ) -> DownloadResult:
        """Download a single video as part of a playlist"""
        try:
            # Configure yt-dlp options
            ydl_opts = self._get_ydl_options(
                playlist_index=playlist_index,
                progress_bar=progress_bar,
                task_id=task_id,
                keep_original=keep_original,
                force=force
            )

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # Extract info first
                info = ydl.extract_info(url, download=False)

                # Check if file already exists
                output_path = self._get_output_path(info, playlist_index=playlist_index)
                if output_path.exists() and not force:
                    logger.info(f"File already exists, skipping: {output_path}")
                    return DownloadResult(
                        file_path=output_path,
                        metadata=self._extract_metadata(info),
                        source_url=url,
                        playlist_index=playlist_index,
                    )

                # Download the file
                info = ydl.extract_info(url, download=True)

                # Get the actual output path - yt-dlp might have sanitized the filename
                expected_path = self._get_output_path(info, playlist_index=playlist_index)

                # Find the actual file created by yt-dlp
                if not expected_path.exists():
                    # Look for files with similar name pattern
                    pattern = f"*{info.get('id', '')}*.wav"
                    matching_files = list(self.output_dir.glob(pattern))
                    if matching_files:
                        output_path = matching_files[0]
                        logger.debug(f"Found actual file by ID: {output_path}")
                    else:
                        # Try with sanitized title
                        sanitized_title = self._sanitize_filename(info.get('title', 'Unknown'))
                        pattern = f"*{sanitized_title.replace(' ', '_')}*.wav"
                        matching_files = list(self.output_dir.glob(pattern))
                        if matching_files:
                            output_path = matching_files[0]
                            logger.debug(f"Found actual file by title: {output_path}")
                        else:
                            # Last resort: find any new WAV file
                            wav_files = list(self.output_dir.glob("*.wav"))
                            if wav_files:
                                # Get the most recently created file
                                output_path = max(wav_files, key=lambda p: p.stat().st_mtime)
                                logger.debug(f"Found actual file by newest: {output_path}")
                            else:
                                output_path = expected_path
                else:
                    output_path = expected_path

                metadata = self._extract_metadata(info)
                metadata['playlist_index'] = playlist_index
                metadata['playlist_total'] = total_videos

                return DownloadResult(
                    file_path=output_path,
                    metadata=metadata,
                    source_url=url,
                    playlist_index=playlist_index,
                )

        except Exception as e:
            logger.error(f"Download failed for video {playlist_index}: {e}")
            return DownloadResult(
                file_path=Path(),
                metadata={},
                source_url=url,
                playlist_index=playlist_index,
                error=str(e)
            )

    def _get_ydl_options(
        self,
        playlist_index: Optional[int] = None,
        progress_bar: Optional[Progress] = None,
        task_id: Optional[int] = None,
        keep_original: bool = False,
        force: bool = False,
    ) -> Dict[str, Any]:
        """Build yt-dlp options dictionary"""
        # Output template - include ID for better matching with non-ASCII titles
        if playlist_index:
            outtmpl = str(self.output_dir / f"{playlist_index:03d}_%(id)s_%(title)s.%(ext)s")
        else:
            outtmpl = str(self.output_dir / "%(id)s_%(title)s.%(ext)s")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': outtmpl,
            'quiet': not logger.isEnabledFor(10),  # DEBUG level
            'no_warnings': not logger.isEnabledFor(20),  # INFO level
            'extract_flat': False,
            'ignoreerrors': False,
            'retries': 3,
            'fragment_retries': 3,
            'skip_download': False,
            'overwrites': force,
            'restrictfilenames': True,  # Avoid problematic characters in filenames
            'windowsfilenames': True,  # Compatible with all OS
        }

        # Audio extraction options
        if not keep_original:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'wav',
                'preferredquality': '0',  # Best quality
            }]

        # Add FFmpeg location if configured
        from .utils.ffmpeg import FFmpegWrapper
        try:
            ffmpeg = FFmpegWrapper()
            ffmpeg_dir = Path(settings.ffmpeg_path).parent
            if ffmpeg_dir != Path('.'):
                ydl_opts['ffmpeg_location'] = str(ffmpeg_dir)
        except Exception:
            pass  # Use system FFmpeg

        # Progress callback
        if progress_bar and task_id is not None:
            callback = DownloadProgressCallback(progress_bar, task_id)
            ydl_opts['progress_hooks'] = [callback]

        return ydl_opts

    def _get_output_path(self, info: Dict[str, Any], playlist_index: Optional[int]) -> Path:
        """Determine the actual output file path"""
        title = self._sanitize_filename(info.get('title', 'Unknown'))
        video_id = info.get('id', '')

        if playlist_index:
            base_name = f"{playlist_index:03d}_{video_id}_{title}"
        else:
            base_name = f"{video_id}_{title}"

        # yt-dlp will have converted to WAV if we requested audio extraction
        return self.output_dir / f"{base_name}.wav"

    def _extract_metadata(self, info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant metadata from yt-dlp info dict"""
        return {
            'title': info.get('title', 'Unknown'),
            'description': info.get('description', ''),
            'uploader': info.get('uploader', 'Unknown'),
            'uploader_id': info.get('uploader_id', ''),
            'channel': info.get('channel', ''),
            'channel_id': info.get('channel_id', ''),
            'duration': info.get('duration', 0),
            'upload_date': info.get('upload_date', ''),
            'view_count': info.get('view_count', 0),
            'like_count': info.get('like_count', 0),
            'categories': info.get('categories', []),
            'tags': info.get('tags', []),
            'thumbnail': info.get('thumbnail', ''),
            'thumbnails': info.get('thumbnails', []),
            'video_id': info.get('id', ''),
            'webpage_url': info.get('webpage_url', ''),
            'original_url': info.get('original_url', ''),
        }

    def _process_local_file(self, file_path: Path) -> DownloadResult:
        """Process a local audio file"""
        from .utils.ffmpeg import FFmpegWrapper

        try:
            # Get audio info
            ffmpeg = FFmpegWrapper()
            audio_info = ffmpeg.get_audio_info(file_path)

            # Create metadata
            metadata = {
                'title': file_path.stem,
                'description': f"Local file: {file_path.name}",
                'duration': audio_info['duration'],
                'format': audio_info['format'],
                'codec': audio_info['codec'],
                'sample_rate': audio_info['sample_rate'],
                'channels': audio_info['channels'],
                'bitrate': audio_info['bitrate'],
                'is_local_file': True,
            }

            return DownloadResult(
                file_path=file_path,
                metadata=metadata,
                source_url=str(file_path),
            )

        except Exception as e:
            logger.error(f"Failed to process local file {file_path}: {e}")
            return DownloadResult(
                file_path=file_path,
                metadata={},
                source_url=str(file_path),
                error=str(e)
            )

    @staticmethod
    def _is_valid_youtube_url(url: str) -> bool:
        """Check if URL is a valid YouTube URL"""
        youtube_regex = re.compile(
            r'(https?://)?(www\.)?(youtube\.com/(watch\?v=|playlist\?list=)|youtu\.be/)'
        )
        return bool(youtube_regex.match(url))

    @staticmethod
    def _is_playlist_url(url: str) -> bool:
        """Check if URL is a YouTube playlist"""
        return 'playlist?list=' in url or '&list=' in url

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitize filename for filesystem compatibility"""
        # Remove or replace problematic characters
        invalid_chars = r'<>:"/\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')

        # Remove leading/trailing whitespace and dots
        filename = filename.strip('. ')

        # Limit length
        max_length = 200
        if len(filename) > max_length:
            filename = filename[:max_length]

        return filename or 'Unknown'