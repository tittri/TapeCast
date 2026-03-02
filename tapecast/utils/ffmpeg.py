"""
FFmpeg wrapper for TapeCast - uses subprocess directly instead of ffmpeg-python
"""

import json
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from ..exceptions import FFmpegError, ProcessingError
from .logger import get_logger


logger = get_logger(__name__)


class FFmpegWrapper:
    """
    Thin wrapper around FFmpeg using subprocess
    Avoids ffmpeg-python which is unmaintained
    """

    def __init__(self, ffmpeg_path: str = "ffmpeg", ffprobe_path: str = "ffprobe"):
        """
        Initialize FFmpeg wrapper

        Args:
            ffmpeg_path: Path to ffmpeg binary
            ffprobe_path: Path to ffprobe binary
        """
        self.ffmpeg_path = ffmpeg_path
        self.ffprobe_path = ffprobe_path
        self._validate_installation()

    def _validate_installation(self) -> None:
        """Check if FFmpeg and FFprobe are available"""
        if not shutil.which(self.ffmpeg_path):
            raise FFmpegError(
                f"FFmpeg not found at '{self.ffmpeg_path}'. "
                "Please install FFmpeg: https://ffmpeg.org/download.html"
            )
        if not shutil.which(self.ffprobe_path):
            raise FFmpegError(
                f"FFprobe not found at '{self.ffprobe_path}'. "
                "FFprobe is usually installed with FFmpeg."
            )

    def get_audio_info(self, file_path: Path) -> Dict[str, Any]:
        """
        Get detailed audio file information using ffprobe

        Args:
            file_path: Path to audio file

        Returns:
            Dictionary with audio metadata
        """
        cmd = [
            self.ffprobe_path,
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            str(file_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=30
            )
            data = json.loads(result.stdout)
        except subprocess.TimeoutExpired:
            raise FFmpegError(f"FFprobe timeout analyzing {file_path}")
        except subprocess.CalledProcessError as e:
            raise FFmpegError(f"FFprobe failed: {e.stderr}")
        except json.JSONDecodeError as e:
            raise FFmpegError(f"Failed to parse FFprobe output: {e}")

        # Extract audio stream info
        audio_stream = None
        for stream in data.get('streams', []):
            if stream.get('codec_type') == 'audio':
                audio_stream = stream
                break

        if not audio_stream:
            raise ProcessingError(f"No audio stream found in {file_path}")

        format_info = data.get('format', {})

        return {
            'duration': float(format_info.get('duration', 0)),
            'duration_str': self._format_duration(float(format_info.get('duration', 0))),
            'size': int(format_info.get('size', 0)),
            'bitrate': int(format_info.get('bit_rate', 0)),
            'format': format_info.get('format_name', ''),
            'sample_rate': int(audio_stream.get('sample_rate', 0)),
            'channels': int(audio_stream.get('channels', 0)),
            'channel_layout': audio_stream.get('channel_layout', ''),
            'codec': audio_stream.get('codec_name', ''),
            'codec_long': audio_stream.get('codec_long_name', ''),
            'bit_depth': audio_stream.get('bits_per_sample', 0),
        }

    def convert_audio(
        self,
        input_path: Path,
        output_path: Path,
        codec: str = "pcm_s16le",
        sample_rate: int = 44100,
        channels: int = 2,
        bitrate: Optional[str] = None,
        additional_args: Optional[List[str]] = None,
        overwrite: bool = True
    ) -> None:
        """
        Convert audio file to different format

        Args:
            input_path: Input audio file
            output_path: Output audio file
            codec: Audio codec (e.g., 'pcm_s16le' for WAV, 'libmp3lame' for MP3)
            sample_rate: Target sample rate
            channels: Number of audio channels
            bitrate: Target bitrate (e.g., '192k')
            additional_args: Additional FFmpeg arguments
            overwrite: Whether to overwrite existing files
        """
        cmd = [
            self.ffmpeg_path,
            '-i', str(input_path),
            '-ar', str(sample_rate),
            '-ac', str(channels),
            '-c:a', codec,
        ]

        if bitrate:
            cmd.extend(['-b:a', bitrate])

        if additional_args:
            cmd.extend(additional_args)

        if overwrite:
            cmd.append('-y')
        else:
            cmd.append('-n')

        cmd.append(str(output_path))

        logger.debug(f"FFmpeg command: {' '.join(cmd)}")
        self._run_ffmpeg(cmd, f"Audio conversion failed: {input_path} -> {output_path}")

    def apply_filters(
        self,
        input_path: Path,
        output_path: Path,
        filters: List[str],
        codec: str = "pcm_s16le",
        sample_rate: int = 44100,
        overwrite: bool = True
    ) -> None:
        """
        Apply audio filters using FFmpeg

        Args:
            input_path: Input audio file
            output_path: Output audio file
            filters: List of filter strings (will be joined with ',')
            codec: Output codec
            sample_rate: Output sample rate
            overwrite: Whether to overwrite existing files
        """
        filter_complex = ','.join(filters)

        cmd = [
            self.ffmpeg_path,
            '-i', str(input_path),
            '-af', filter_complex,
            '-c:a', codec,
            '-ar', str(sample_rate),
        ]

        if overwrite:
            cmd.append('-y')
        else:
            cmd.append('-n')

        cmd.append(str(output_path))

        logger.debug(f"Applying filters: {filter_complex}")
        self._run_ffmpeg(cmd, f"Filter application failed on {input_path}")

    def loudness_normalize(
        self,
        input_path: Path,
        output_path: Path,
        target_lufs: float = -16.0,
        codec: str = "pcm_s16le",
        sample_rate: int = 44100,
        bitrate: Optional[str] = None,
        two_pass: bool = True
    ) -> None:
        """
        Apply loudness normalization using FFmpeg's loudnorm filter

        Args:
            input_path: Input audio file
            output_path: Output audio file
            target_lufs: Target loudness in LUFS
            codec: Output codec
            sample_rate: Output sample rate
            bitrate: Output bitrate
            two_pass: Use two-pass normalization for better accuracy
        """
        if two_pass:
            try:
                # First pass: analyze audio
                measured = self._measure_loudness(input_path, target_lufs)

                # Second pass: apply normalization with measured values
                filter_str = (
                    f"loudnorm="
                    f"I={target_lufs}:"
                    f"TP=-1.5:"
                    f"LRA=11:"
                    f"measured_I={measured['input_i']}:"
                    f"measured_TP={measured['input_tp']}:"
                    f"measured_LRA={measured['input_lra']}:"
                    f"measured_thresh={measured['input_thresh']}:"
                    f"offset={measured.get('target_offset', 0)}:"
                    f"linear=true"
                )
            except FFmpegError as e:
                # Fallback to single-pass if measurement fails
                logger.warning(f"Two-pass normalization failed, using single-pass: {e}")
                filter_str = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"
        else:
            # Single pass normalization
            filter_str = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11"

        cmd = [
            self.ffmpeg_path,
            '-i', str(input_path),
            '-af', filter_str,
            '-c:a', codec,
            '-ar', str(sample_rate),
        ]

        if bitrate:
            cmd.extend(['-b:a', bitrate])

        cmd.extend(['-y', str(output_path)])

        logger.debug(f"Loudness normalization: {filter_str}")
        self._run_ffmpeg(cmd, f"Loudness normalization failed on {input_path}")

    def _measure_loudness(self, input_path: Path, target_lufs: float) -> Dict[str, float]:
        """
        Measure loudness of audio file (first pass of two-pass normalization)

        Args:
            input_path: Input audio file
            target_lufs: Target loudness for normalization

        Returns:
            Dictionary with measured loudness values
        """
        filter_str = f"loudnorm=I={target_lufs}:TP=-1.5:LRA=11:print_format=json"

        cmd = [
            self.ffmpeg_path,
            '-i', str(input_path),
            '-af', filter_str,
            '-f', 'null',
            '-'
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,  # Don't check return code - FFmpeg returns non-zero for null output
                timeout=120
            )

            # Parse loudness stats from stderr (FFmpeg outputs this to stderr)
            stderr_lines = result.stderr.split('\n')
            json_start = None
            json_end = None

            for i, line in enumerate(stderr_lines):
                if '[Parsed_loudnorm' in line and '{' in line:
                    json_start = i
                if json_start is not None and '}' in line:
                    json_end = i + 1
                    break

            if json_start is not None and json_end is not None:
                json_lines = stderr_lines[json_start:json_end]
                json_str = '\n'.join(json_lines)
                # Extract JSON from the line
                json_str = json_str[json_str.index('{'):]
                loudness_stats = json.loads(json_str)
                return loudness_stats

            raise FFmpegError("Could not parse loudness measurements from FFmpeg output")

        except subprocess.TimeoutExpired:
            raise FFmpegError(f"Loudness measurement timeout on {input_path}")
        except json.JSONDecodeError as e:
            raise FFmpegError(f"Failed to parse loudness measurements: {e}")
        except Exception as e:
            raise FFmpegError(f"Loudness measurement failed: {e}")

    def create_video_from_audio(
        self,
        audio_path: Path,
        image_path: Path,
        output_path: Path,
        video_codec: str = "libx264",
        audio_codec: str = "aac",
        audio_bitrate: str = "192k",
        fps: int = 1,
        overwrite: bool = True
    ) -> None:
        """
        Create a video file from an audio file and a static image

        Args:
            audio_path: Input audio file
            image_path: Input image file (thumbnail)
            output_path: Output video file
            video_codec: Video codec to use
            audio_codec: Audio codec for video
            audio_bitrate: Audio bitrate for video
            fps: Frames per second (1 for static image)
            overwrite: Whether to overwrite existing files
        """
        cmd = [
            self.ffmpeg_path,
            '-loop', '1',
            '-framerate', str(fps),
            '-i', str(image_path),
            '-i', str(audio_path),
            '-c:v', video_codec,
            '-tune', 'stillimage',
            '-c:a', audio_codec,
            '-b:a', audio_bitrate,
            '-shortest',
            '-pix_fmt', 'yuv420p',  # For compatibility
        ]

        if overwrite:
            cmd.append('-y')
        else:
            cmd.append('-n')

        cmd.append(str(output_path))

        logger.debug(f"Creating video from audio and image")
        self._run_ffmpeg(cmd, f"Video creation failed")

    def extract_audio(
        self,
        input_path: Path,
        output_path: Path,
        codec: str = "pcm_s16le",
        sample_rate: int = 44100,
        channels: int = 2,
        overwrite: bool = True
    ) -> None:
        """
        Extract audio from video file

        Args:
            input_path: Input video file
            output_path: Output audio file
            codec: Audio codec
            sample_rate: Sample rate
            channels: Number of channels
            overwrite: Whether to overwrite existing files
        """
        cmd = [
            self.ffmpeg_path,
            '-i', str(input_path),
            '-vn',  # No video
            '-c:a', codec,
            '-ar', str(sample_rate),
            '-ac', str(channels),
        ]

        if overwrite:
            cmd.append('-y')
        else:
            cmd.append('-n')

        cmd.append(str(output_path))

        self._run_ffmpeg(cmd, f"Audio extraction failed from {input_path}")

    def _run_ffmpeg(
        self,
        cmd: List[str],
        error_message: str,
        timeout: int = 300
    ) -> Tuple[str, str]:
        """
        Run FFmpeg command and handle errors

        Args:
            cmd: Command to run
            error_message: Error message prefix
            timeout: Command timeout in seconds

        Returns:
            Tuple of (stdout, stderr)
        """
        logger.debug(f"Running: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=timeout
            )
            return result.stdout, result.stderr

        except subprocess.TimeoutExpired:
            raise FFmpegError(f"{error_message}: Operation timed out after {timeout} seconds")
        except subprocess.CalledProcessError as e:
            # Parse FFmpeg error from stderr
            error_lines = e.stderr.split('\n') if e.stderr else []
            error_detail = next(
                (line for line in error_lines if 'error' in line.lower()),
                e.stderr[:500] if e.stderr else "Unknown error"
            )
            raise FFmpegError(f"{error_message}: {error_detail}")
        except Exception as e:
            raise FFmpegError(f"{error_message}: {str(e)}")

    @staticmethod
    def _format_duration(seconds: float) -> str:
        """Format duration in seconds to HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    @staticmethod
    def get_format_info() -> Dict[str, Dict[str, str]]:
        """Get information about supported audio formats"""
        return {
            'mp3': {'codec': 'libmp3lame', 'extension': 'mp3', 'mime': 'audio/mpeg'},
            'flac': {'codec': 'flac', 'extension': 'flac', 'mime': 'audio/flac'},
            'wav': {'codec': 'pcm_s16le', 'extension': 'wav', 'mime': 'audio/wav'},
            'opus': {'codec': 'libopus', 'extension': 'opus', 'mime': 'audio/opus'},
            'm4a': {'codec': 'aac', 'extension': 'm4a', 'mime': 'audio/mp4'},
        }