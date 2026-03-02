"""
Three-stage audio enhancement pipeline for TapeCast

Stage 1: FFmpeg preprocessing (high-pass, hum removal, de-click/de-crackle)
Stage 2: Python processing (spectral noise reduction, EQ, compression)
Stage 3: FFmpeg final processing (loudness normalization, encoding)
"""

import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import soundfile as sf
import noisereduce as nr
from pedalboard import (
    Pedalboard,
    Compressor,
    Gain,
    NoiseGate,
    Distortion,
    HighShelfFilter,
    LowShelfFilter,
    PeakFilter,
)
from .profiles import EnhancementProfile, ProfileManager, ProfileType
from .utils.ffmpeg import FFmpegWrapper
from .utils.audio import load_audio, save_audio, get_audio_stats
from .utils.progress import ProgressTracker
from .utils.logger import get_logger, console
from .exceptions import ProcessingError
from .config import settings


logger = get_logger(__name__)


class AudioEnhancer:
    """
    Three-stage audio enhancement pipeline

    Processes audio through:
    1. FFmpeg preprocessing (filters, hum removal)
    2. Python processing (noise reduction, EQ, compression)
    3. FFmpeg final processing (loudness, encoding)
    """

    def __init__(self):
        """Initialize the audio enhancer"""
        self.ffmpeg = FFmpegWrapper(
            ffmpeg_path=settings.ffmpeg_path,
            ffprobe_path=settings.ffprobe_path
        )
        self.temp_dir = None

    def enhance(
        self,
        input_path: Path,
        output_path: Path,
        profile: Optional[EnhancementProfile] = None,
        target_format: str = "mp3",
        target_bitrate: str = "192k",
        target_loudness: float = -16.0,
        progress_tracker: Optional[ProgressTracker] = None,
        force: bool = False,
    ) -> Path:
        """
        Main enhancement pipeline

        Args:
            input_path: Input audio file
            output_path: Output audio file
            profile: Enhancement profile to use
            target_format: Output format (mp3, flac, wav, opus, m4a)
            target_bitrate: Output bitrate for lossy formats
            target_loudness: Target loudness in LUFS
            progress_tracker: Optional progress tracker
            force: Force reprocessing even if output exists

        Returns:
            Path to enhanced audio file
        """
        # Check if output exists
        if output_path.exists() and not force:
            logger.info(f"Output already exists, skipping: {output_path}")
            return output_path

        # Auto-detect profile if not provided
        if profile is None:
            if isinstance(profile, str) and profile.lower() == "auto":
                profile = ProfileManager.auto_detect(input_path)
            else:
                profile = ProfileManager.get_profile(ProfileType.AUTO)
                if profile.name == "auto":
                    profile = ProfileManager.auto_detect(input_path)

        logger.info(f"Enhancing audio with profile: {profile.name}")
        logger.debug(f"Input: {input_path}")
        logger.debug(f"Output: {output_path}")

        # Create temporary directory for intermediate files
        with tempfile.TemporaryDirectory(prefix="tapecast_") as temp_dir:
            self.temp_dir = Path(temp_dir)

            try:
                # Create intermediate file paths
                stage1_output = self.temp_dir / "stage1.wav"
                stage2_output = self.temp_dir / "stage2.wav"

                # Initialize progress tracker
                if progress_tracker:
                    progress_tracker.total_stages = 3

                # Stage 1: FFmpeg preprocessing
                if progress_tracker:
                    progress_tracker.start_stage(1, "FFmpeg preprocessing", 100)

                self._stage1_ffmpeg_preprocessing(
                    input_path, stage1_output, profile, progress_tracker
                )

                if progress_tracker:
                    progress_tracker.complete_stage()

                # Stage 2: Python processing
                if progress_tracker:
                    progress_tracker.start_stage(2, "Audio enhancement", 100)

                self._stage2_python_processing(
                    stage1_output, stage2_output, profile, progress_tracker
                )

                if progress_tracker:
                    progress_tracker.complete_stage()

                # Stage 3: FFmpeg final processing
                if progress_tracker:
                    progress_tracker.start_stage(3, "Final processing", 100)

                self._stage3_ffmpeg_final(
                    stage2_output,
                    output_path,
                    profile,
                    target_format,
                    target_bitrate,
                    target_loudness,
                    progress_tracker,
                )

                if progress_tracker:
                    progress_tracker.complete_stage()
                    progress_tracker.complete()

                logger.info(f"Enhancement complete: {output_path}")
                return output_path

            except Exception as e:
                logger.error(f"Enhancement failed: {e}")
                raise ProcessingError(f"Audio enhancement failed: {e}")

    def _stage1_ffmpeg_preprocessing(
        self,
        input_path: Path,
        output_path: Path,
        profile: EnhancementProfile,
        progress: Optional[ProgressTracker] = None,
    ) -> None:
        """
        Stage 1: FFmpeg preprocessing
        - High-pass filter
        - Hum removal (notch filters)
        - De-click / de-crackle
        """
        logger.debug(f"Stage 1: FFmpeg preprocessing with profile {profile.name}")

        # Build filter chain
        filters = profile.get_stage1_filters()

        if not filters:
            # No filters needed, just convert to WAV
            logger.debug("No Stage 1 filters needed, converting to WAV")
            self.ffmpeg.convert_audio(
                input_path,
                output_path,
                codec="pcm_s16le",
                sample_rate=settings.sample_rate,
                channels=2,
            )
        else:
            # Apply filters
            logger.debug(f"Applying {len(filters)} filters: {filters}")
            self.ffmpeg.apply_filters(
                input_path,
                output_path,
                filters,
                codec="pcm_s16le",
                sample_rate=settings.sample_rate,
            )

        if progress:
            progress.update_stage(100)

        # Verify output
        if not output_path.exists():
            raise ProcessingError(f"Stage 1 failed to create output file: {output_path}")

        logger.debug(f"Stage 1 complete: {output_path}")

    def _stage2_python_processing(
        self,
        input_path: Path,
        output_path: Path,
        profile: EnhancementProfile,
        progress: Optional[ProgressTracker] = None,
    ) -> None:
        """
        Stage 2: Python processing
        - Spectral noise reduction (noisereduce)
        - EQ (pedalboard)
        - Compression (pedalboard)
        """
        logger.debug(f"Stage 2: Python processing with profile {profile.name}")

        # Load audio
        audio_data, sample_rate = load_audio(input_path, sample_rate=settings.sample_rate)

        # Get processing parameters
        params = profile.get_stage2_params()

        # Step 1: Spectral noise reduction
        if params['noise_reduction']['prop_decrease'] > 0:
            logger.debug(f"Applying noise reduction: {params['noise_reduction']}")
            if progress:
                progress.update_stage(30, "Applying noise reduction")

            # Convert to the format expected by noisereduce (samples, channels)
            if audio_data.ndim == 2:
                # Transpose from (channels, samples) to (samples, channels)
                audio_for_nr = audio_data.T
            else:
                audio_for_nr = audio_data.reshape(-1, 1)

            # Apply noise reduction
            try:
                audio_reduced = nr.reduce_noise(
                    y=audio_for_nr,
                    sr=sample_rate,
                    prop_decrease=params['noise_reduction']['prop_decrease'],
                    stationary=True,  # Assume stationary noise like tape hiss
                )

                # Convert back to (channels, samples)
                if audio_reduced.ndim == 2:
                    audio_data = audio_reduced.T
                else:
                    audio_data = audio_reduced.reshape(1, -1)

            except Exception as e:
                logger.warning(f"Noise reduction failed: {e}. Skipping...")

        # Step 2: EQ and Compression with Pedalboard
        if params['eq'] or params['compressor']['ratio'] > 1.0:
            logger.debug("Applying EQ and compression")
            if progress:
                progress.update_stage(60, "Applying EQ and compression")

            # Build pedalboard chain
            board = Pedalboard()

            # Add EQ filters
            for freq, gain_db in params['eq'].items():
                if gain_db == 0:
                    continue

                if freq < 300:
                    # Low shelf for bass frequencies
                    board.append(
                        LowShelfFilter(
                            cutoff_frequency_hz=freq,
                            gain_db=gain_db,
                            q=0.7,
                        )
                    )
                elif freq > 5000:
                    # High shelf for treble frequencies
                    board.append(
                        HighShelfFilter(
                            cutoff_frequency_hz=freq,
                            gain_db=gain_db,
                            q=0.7,
                        )
                    )
                else:
                    # Peak filter for mid frequencies
                    board.append(
                        PeakFilter(
                            cutoff_frequency_hz=freq,
                            gain_db=gain_db,
                            q=1.0,
                        )
                    )

            # Add compressor
            if params['compressor']['ratio'] > 1.0:
                board.append(
                    Compressor(
                        threshold_db=params['compressor']['threshold_db'],
                        ratio=params['compressor']['ratio'],
                        attack_ms=params['compressor']['attack_ms'],
                        release_ms=params['compressor']['release_ms'],
                    )
                )

            # Apply the board
            if len(board) > 0:
                # Ensure audio is in the right format (channels, samples)
                audio_data = board(audio_data, sample_rate)

        # Step 3: Save processed audio
        if progress:
            progress.update_stage(90, "Saving processed audio")

        save_audio(output_path, audio_data, sample_rate, normalize=True)

        if progress:
            progress.update_stage(100)

        # Verify output
        if not output_path.exists():
            raise ProcessingError(f"Stage 2 failed to create output file: {output_path}")

        logger.debug(f"Stage 2 complete: {output_path}")

    def _stage3_ffmpeg_final(
        self,
        input_path: Path,
        output_path: Path,
        profile: EnhancementProfile,
        target_format: str,
        target_bitrate: str,
        target_loudness: float,
        progress: Optional[ProgressTracker] = None,
    ) -> None:
        """
        Stage 3: FFmpeg final processing
        - Two-pass loudness normalization
        - Output encoding
        """
        logger.debug(f"Stage 3: Final processing to {target_format}")

        # Get codec info for target format
        format_info = FFmpegWrapper.get_format_info()
        if target_format not in format_info:
            raise ProcessingError(f"Unsupported format: {target_format}")

        codec_info = format_info[target_format]
        codec = codec_info['codec']

        # Apply any Stage 3 filters (currently none, but could add in future)
        stage3_filters = profile.get_stage3_filters()

        if progress:
            progress.update_stage(30, "Normalizing loudness")

        # Two-pass loudness normalization
        if profile.name != "none":  # Skip normalization for "none" profile
            temp_normalized = self.temp_dir / "normalized.wav"

            # Use the profile's target loudness or the override
            final_loudness = target_loudness or profile.loudness_target_lufs

            self.ffmpeg.loudness_normalize(
                input_path,
                temp_normalized,
                target_lufs=final_loudness,
                codec="pcm_s16le",
                sample_rate=settings.sample_rate,
                two_pass=True,
            )
            input_path = temp_normalized

        if progress:
            progress.update_stage(70, f"Encoding to {target_format}")

        # Final encoding
        bitrate = None if target_format in ['wav', 'flac'] else target_bitrate

        self.ffmpeg.convert_audio(
            input_path,
            output_path,
            codec=codec,
            sample_rate=settings.sample_rate,
            channels=2,
            bitrate=bitrate,
            additional_args=stage3_filters if stage3_filters else None,
        )

        if progress:
            progress.update_stage(100)

        # Verify output
        if not output_path.exists():
            raise ProcessingError(f"Stage 3 failed to create output file: {output_path}")

        # Log final stats
        try:
            final_info = self.ffmpeg.get_audio_info(output_path)
            logger.info(
                f"Final output: {target_format}, "
                f"{final_info['duration_str']}, "
                f"{final_info['bitrate'] // 1000}kbps, "
                f"{final_info['sample_rate']}Hz"
            )
        except Exception as e:
            logger.debug(f"Could not get final audio info: {e}")

        logger.debug(f"Stage 3 complete: {output_path}")

    def process_batch(
        self,
        input_files: List[Path],
        output_dir: Path,
        profile: Optional[EnhancementProfile] = None,
        target_format: str = "mp3",
        target_bitrate: str = "192k",
        target_loudness: float = -16.0,
        force: bool = False,
    ) -> List[Tuple[Path, bool, Optional[str]]]:
        """
        Process multiple audio files in batch

        Args:
            input_files: List of input audio files
            output_dir: Output directory
            profile: Enhancement profile to use
            target_format: Output format
            target_bitrate: Output bitrate
            target_loudness: Target loudness
            force: Force reprocessing

        Returns:
            List of (output_path, success, error_message) tuples
        """
        results = []
        total = len(input_files)

        console.print(f"\n[cyan]Processing {total} files[/cyan]")

        for idx, input_file in enumerate(input_files, 1):
            console.print(f"\n[dim]Processing {idx}/{total}: {input_file.name}[/dim]")

            # Generate output filename
            output_name = f"{input_file.stem}_enhanced.{target_format}"
            output_path = output_dir / output_name

            try:
                # Create progress tracker
                with ProgressTracker(
                    total_stages=3,
                    description=f"Processing {input_file.name}"
                ) as tracker:
                    self.enhance(
                        input_file,
                        output_path,
                        profile=profile,
                        target_format=target_format,
                        target_bitrate=target_bitrate,
                        target_loudness=target_loudness,
                        progress_tracker=tracker,
                        force=force,
                    )

                results.append((output_path, True, None))
                console.print(f"  [green]✓[/green] {output_path.name}")

            except Exception as e:
                error_msg = str(e)
                results.append((output_path, False, error_msg))
                console.print(f"  [red]✗[/red] Failed: {error_msg}")
                logger.error(f"Failed to process {input_file}: {e}")

        # Summary
        success_count = sum(1 for _, success, _ in results if success)
        console.print(f"\n[green]Processed {success_count}/{total} files successfully[/green]")

        return results