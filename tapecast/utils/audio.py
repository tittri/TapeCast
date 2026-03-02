"""
Audio processing utilities for TapeCast
"""

import numpy as np
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import soundfile as sf
from scipy import signal
from .logger import get_logger


logger = get_logger(__name__)


def load_audio(file_path: Path, sample_rate: Optional[int] = None) -> Tuple[np.ndarray, int]:
    """
    Load audio file and return samples and sample rate

    Args:
        file_path: Path to audio file
        sample_rate: Target sample rate (resamples if different)

    Returns:
        Tuple of (audio_data, sample_rate)
        audio_data shape: (channels, samples)
    """
    try:
        data, sr = sf.read(str(file_path), always_2d=True)
        # Transpose to (channels, samples) format
        data = data.T

        # Resample if needed
        if sample_rate and sr != sample_rate:
            data = resample_audio(data, sr, sample_rate)
            sr = sample_rate

        return data, sr

    except Exception as e:
        raise IOError(f"Failed to load audio file {file_path}: {e}")


def save_audio(
    file_path: Path,
    audio_data: np.ndarray,
    sample_rate: int,
    normalize: bool = True
) -> None:
    """
    Save audio data to file

    Args:
        file_path: Output file path
        audio_data: Audio data with shape (channels, samples)
        sample_rate: Sample rate
        normalize: Whether to normalize to [-1, 1] range
    """
    try:
        # Ensure audio is in correct range
        if normalize:
            max_val = np.max(np.abs(audio_data))
            if max_val > 0:
                audio_data = audio_data / max_val * 0.95  # Leave some headroom

        # Transpose back to (samples, channels) for soundfile
        if audio_data.ndim == 2:
            audio_data = audio_data.T
        elif audio_data.ndim == 1:
            audio_data = audio_data.reshape(-1, 1)

        sf.write(str(file_path), audio_data, sample_rate)
        logger.debug(f"Saved audio to {file_path}")

    except Exception as e:
        raise IOError(f"Failed to save audio file {file_path}: {e}")


def resample_audio(
    audio_data: np.ndarray,
    orig_sr: int,
    target_sr: int
) -> np.ndarray:
    """
    Resample audio to different sample rate

    Args:
        audio_data: Audio data with shape (channels, samples)
        orig_sr: Original sample rate
        target_sr: Target sample rate

    Returns:
        Resampled audio data
    """
    if orig_sr == target_sr:
        return audio_data

    # Calculate resampling ratio
    ratio = target_sr / orig_sr

    # Resample each channel
    if audio_data.ndim == 2:
        num_channels, num_samples = audio_data.shape
        new_length = int(num_samples * ratio)
        resampled = np.zeros((num_channels, new_length))

        for ch in range(num_channels):
            resampled[ch] = signal.resample(audio_data[ch], new_length)
    else:
        new_length = int(len(audio_data) * ratio)
        resampled = signal.resample(audio_data, new_length)

    return resampled


def get_audio_stats(audio_data: np.ndarray, sample_rate: int) -> Dict[str, Any]:
    """
    Calculate statistics about audio data

    Args:
        audio_data: Audio data with shape (channels, samples)
        sample_rate: Sample rate

    Returns:
        Dictionary with audio statistics
    """
    if audio_data.ndim == 2:
        num_channels, num_samples = audio_data.shape
    else:
        num_channels = 1
        num_samples = len(audio_data)
        audio_data = audio_data.reshape(1, -1)

    duration = num_samples / sample_rate

    # Calculate RMS for each channel
    rms_per_channel = []
    peak_per_channel = []
    for ch in range(num_channels):
        rms = np.sqrt(np.mean(audio_data[ch] ** 2))
        peak = np.max(np.abs(audio_data[ch]))
        rms_per_channel.append(rms)
        peak_per_channel.append(peak)

    # Calculate overall stats
    overall_rms = np.mean(rms_per_channel)
    overall_peak = np.max(peak_per_channel)

    # Convert to dB
    rms_db = 20 * np.log10(overall_rms + 1e-10)
    peak_db = 20 * np.log10(overall_peak + 1e-10)

    # Estimate loudness (simplified LUFS approximation)
    # This is a rough estimate, not true LUFS
    loudness_lufs = rms_db + 10  # Rough approximation

    return {
        'duration': duration,
        'num_channels': num_channels,
        'num_samples': num_samples,
        'sample_rate': sample_rate,
        'rms': overall_rms,
        'rms_db': rms_db,
        'peak': overall_peak,
        'peak_db': peak_db,
        'loudness_lufs_approx': loudness_lufs,
        'rms_per_channel': rms_per_channel,
        'peak_per_channel': peak_per_channel,
    }


def detect_silence(
    audio_data: np.ndarray,
    sample_rate: int,
    threshold_db: float = -40,
    min_duration: float = 0.5
) -> list[Tuple[float, float]]:
    """
    Detect silence segments in audio

    Args:
        audio_data: Audio data with shape (channels, samples)
        sample_rate: Sample rate
        threshold_db: Silence threshold in dB
        min_duration: Minimum duration for silence segment in seconds

    Returns:
        List of (start_time, end_time) tuples for silence segments
    """
    # Convert to mono if stereo
    if audio_data.ndim == 2:
        mono = np.mean(audio_data, axis=0)
    else:
        mono = audio_data

    # Convert threshold to linear
    threshold_linear = 10 ** (threshold_db / 20)

    # Find samples below threshold
    is_silence = np.abs(mono) < threshold_linear

    # Find silence segments
    silence_segments = []
    min_samples = int(min_duration * sample_rate)

    # Find transitions
    diff = np.diff(np.concatenate(([False], is_silence, [False])).astype(int))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]

    for start, end in zip(starts, ends):
        duration_samples = end - start
        if duration_samples >= min_samples:
            start_time = start / sample_rate
            end_time = end / sample_rate
            silence_segments.append((start_time, end_time))

    return silence_segments


def trim_silence(
    audio_data: np.ndarray,
    sample_rate: int,
    threshold_db: float = -40,
    min_silence_duration: float = 0.5,
    trim_start: bool = True,
    trim_end: bool = True,
    padding: float = 0.1
) -> np.ndarray:
    """
    Trim silence from beginning and/or end of audio

    Args:
        audio_data: Audio data with shape (channels, samples)
        sample_rate: Sample rate
        threshold_db: Silence threshold in dB
        min_silence_duration: Minimum duration to consider as silence
        trim_start: Whether to trim silence from beginning
        trim_end: Whether to trim silence from end
        padding: Seconds of padding to leave after detected audio

    Returns:
        Trimmed audio data
    """
    if not trim_start and not trim_end:
        return audio_data

    # Convert to mono for silence detection
    if audio_data.ndim == 2:
        mono = np.mean(audio_data, axis=0)
        is_stereo = True
    else:
        mono = audio_data
        is_stereo = False

    # Convert threshold to linear
    threshold_linear = 10 ** (threshold_db / 20)

    # Find samples above threshold (non-silence)
    is_audio = np.abs(mono) >= threshold_linear

    if not np.any(is_audio):
        # All silence, return minimal audio to avoid empty file
        logger.warning("Audio is all silence, returning minimal audio")
        return audio_data[:, :int(sample_rate * 0.1)] if is_stereo else audio_data[:int(sample_rate * 0.1)]

    # Find first and last non-silence samples
    non_silence_indices = np.where(is_audio)[0]

    # Add padding in samples
    padding_samples = int(padding * sample_rate)

    # Calculate trim points
    start_sample = 0
    end_sample = len(mono)

    if trim_start and len(non_silence_indices) > 0:
        start_sample = max(0, non_silence_indices[0] - padding_samples)
        logger.debug(f"Trimming {start_sample / sample_rate:.2f}s from start")

    if trim_end and len(non_silence_indices) > 0:
        end_sample = min(len(mono), non_silence_indices[-1] + padding_samples)
        trimmed_end = (len(mono) - end_sample) / sample_rate
        if trimmed_end > 0:
            logger.debug(f"Trimming {trimmed_end:.2f}s from end")

    # Apply trim
    if is_stereo:
        return audio_data[:, start_sample:end_sample]
    else:
        return audio_data[start_sample:end_sample]


def analyze_frequency_content(
    audio_data: np.ndarray,
    sample_rate: int,
    freq_bands: Optional[list[Tuple[float, float]]] = None
) -> Dict[str, float]:
    """
    Analyze frequency content of audio

    Args:
        audio_data: Audio data with shape (channels, samples)
        sample_rate: Sample rate
        freq_bands: List of (low_freq, high_freq) tuples for analysis

    Returns:
        Dictionary with energy in each frequency band
    """
    if freq_bands is None:
        freq_bands = [
            (0, 100),      # Sub-bass
            (100, 250),    # Bass
            (250, 500),    # Low mids
            (500, 2000),   # Mids
            (2000, 4000),  # High mids
            (4000, 8000),  # Presence
            (8000, 20000), # Brilliance
        ]

    # Convert to mono if stereo
    if audio_data.ndim == 2:
        mono = np.mean(audio_data, axis=0)
    else:
        mono = audio_data

    # Compute FFT
    fft = np.fft.rfft(mono)
    freqs = np.fft.rfftfreq(len(mono), 1/sample_rate)
    magnitude = np.abs(fft)

    # Calculate energy in each band
    band_energy = {}
    total_energy = np.sum(magnitude ** 2)

    for low_freq, high_freq in freq_bands:
        # Find indices for frequency range
        band_mask = (freqs >= low_freq) & (freqs < high_freq)
        band_mag = magnitude[band_mask]

        # Calculate relative energy
        if len(band_mag) > 0:
            energy = np.sum(band_mag ** 2)
            relative_energy = energy / total_energy if total_energy > 0 else 0
            band_energy[f"{int(low_freq)}-{int(high_freq)}Hz"] = relative_energy
        else:
            band_energy[f"{int(low_freq)}-{int(high_freq)}Hz"] = 0.0

    return band_energy


def detect_audio_profile_heuristics(audio_path: Path) -> str:
    """
    Auto-detect best audio profile based on audio characteristics

    Args:
        audio_path: Path to audio file

    Returns:
        Recommended profile name
    """
    try:
        # Load first 30 seconds for analysis
        audio_data, sample_rate = load_audio(audio_path)
        max_samples = 30 * sample_rate
        if audio_data.shape[1] > max_samples:
            audio_data = audio_data[:, :max_samples]

        # Get audio statistics
        stats = get_audio_stats(audio_data, sample_rate)

        # Detect silence segments
        silence_segments = detect_silence(audio_data, sample_rate, threshold_db=-50)

        # Analyze frequency content
        freq_analysis = analyze_frequency_content(audio_data, sample_rate)

        # Decision logic based on PRD specifications
        noise_floor_db = stats['rms_db']

        # Check noise floor
        if noise_floor_db > -35:
            # High ambient noise
            logger.debug(f"High noise floor detected: {noise_floor_db:.1f} dB -> phone profile")
            return "phone"
        elif -50 <= noise_floor_db <= -35:
            # Moderate tape noise
            logger.debug(f"Moderate noise floor detected: {noise_floor_db:.1f} dB -> vhs profile")
            return "vhs"
        elif -65 <= noise_floor_db < -50:
            # Light tape hiss
            logger.debug(f"Light noise floor detected: {noise_floor_db:.1f} dB -> cassette profile")
            return "cassette"
        elif noise_floor_db < -65:
            # Already decent quality
            logger.debug(f"Low noise floor detected: {noise_floor_db:.1f} dB -> clean profile")
            return "clean"

        # Default to cassette if uncertain
        logger.debug("Uncertain audio characteristics -> defaulting to cassette profile")
        return "cassette"

    except Exception as e:
        logger.warning(f"Failed to auto-detect profile: {e}. Using cassette as default.")
        return "cassette"