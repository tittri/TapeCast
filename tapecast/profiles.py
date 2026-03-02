"""
Audio enhancement profiles for TapeCast

Defines presets for different audio source types (cassette, VHS, phone, etc.)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum
from pathlib import Path
from .exceptions import ProfileError
from .utils.logger import get_logger


logger = get_logger(__name__)


class ProfileType(Enum):
    """Available enhancement profile types"""
    AUTO = "auto"
    CASSETTE = "cassette"
    VHS = "vhs"
    PHONE = "phone"
    CLEAN = "clean"
    NONE = "none"


@dataclass
class FilterSpec:
    """Specification for an audio filter"""
    name: str
    params: Dict[str, any]
    stage: int  # Which stage (1, 2, or 3) this filter belongs to


@dataclass
class EnhancementProfile:
    """
    Audio enhancement profile configuration
    Defines all parameters for the three-stage processing pipeline
    """
    name: str
    description: str

    # Stage 1: FFmpeg preprocessing
    highpass_freq: int = 80
    hum_freq: Optional[int] = 60  # 50 or 60 Hz, None to skip
    hum_harmonics: List[int] = field(default_factory=lambda: [2, 3])  # Multiples of hum_freq
    hum_q: float = 5.0
    hum_gain_db: float = -25.0
    use_declick: bool = False
    use_decrackle: bool = False

    # Stage 2: Python processing (noisereduce + pedalboard)
    noise_reduce_prop: float = 0.7  # 0.0-1.0, aggressiveness
    noise_freq_mask_smooth_hz: int = 500
    eq_bands: Dict[float, float] = field(default_factory=dict)  # freq_hz: gain_db
    compressor_threshold_db: float = -20.0
    compressor_ratio: float = 3.0
    compressor_attack_ms: float = 10.0
    compressor_release_ms: float = 200.0

    # Stage 3: FFmpeg final processing
    loudness_target_lufs: float = -16.0
    loudness_tp: float = -1.5  # True peak
    loudness_lra: float = 11.0  # Loudness range

    def get_stage1_filters(self) -> List[str]:
        """
        Get FFmpeg filter chain for Stage 1
        Returns list of filter strings to be combined
        """
        filters = []

        # High-pass filter
        if self.highpass_freq > 0:
            filters.append(f"highpass=f={self.highpass_freq}")

        # Hum removal (notch filters)
        if self.hum_freq:
            for harmonic in [1] + self.hum_harmonics:
                freq = self.hum_freq * harmonic
                if freq < 20000:  # Stay within audible range
                    # Using equalizer as notch filter
                    filters.append(
                        f"equalizer=f={freq}:t=q:w={self.hum_q}:g={self.hum_gain_db}"
                    )

        # De-click filter
        if self.use_declick:
            filters.append("adeclick")

        # De-crackle filter
        if self.use_decrackle:
            filters.append("adecrackle")

        return filters

    def get_stage2_params(self) -> Dict[str, any]:
        """Get parameters for Stage 2 Python processing"""
        return {
            'noise_reduction': {
                'prop_decrease': self.noise_reduce_prop,
                'freq_mask_smooth_hz': self.noise_freq_mask_smooth_hz,
            },
            'eq': self.eq_bands,
            'compressor': {
                'threshold_db': self.compressor_threshold_db,
                'ratio': self.compressor_ratio,
                'attack_ms': self.compressor_attack_ms,
                'release_ms': self.compressor_release_ms,
            }
        }

    def get_stage3_filters(self) -> List[str]:
        """Get FFmpeg filter chain for Stage 3 (placeholder for now)"""
        # Loudness normalization is handled separately with two-pass
        # This could include additional character filters in the future
        return []


class ProfileManager:
    """Manage and retrieve audio enhancement profiles"""

    # Define all profiles according to PRD specifications
    PROFILES = {
        ProfileType.CASSETTE: EnhancementProfile(
            name="cassette",
            description="Classic cassette tape restoration - warm analog sound with light enhancement",
            highpass_freq=65,
            hum_freq=50,  # Will be detected automatically
            hum_harmonics=[2, 3],  # 100Hz, 150Hz
            hum_q=5.0,
            hum_gain_db=-25.0,
            use_declick=True,
            use_decrackle=False,
            noise_reduce_prop=0.7,
            noise_freq_mask_smooth_hz=500,
            eq_bands={
                200.0: -3.0,   # Cut 200-400Hz by -3dB (mud)
                300.0: -3.0,
                400.0: -3.0,
                3000.0: 4.0,   # Shelf boost 3kHz+ by +4dB (clarity)
                5000.0: 4.0,
                8000.0: 3.0,
            },
            compressor_threshold_db=-20.0,
            compressor_ratio=3.0,
            compressor_attack_ms=10.0,
            compressor_release_ms=200.0,
        ),

        ProfileType.VHS: EnhancementProfile(
            name="vhs",
            description="VHS tape restoration - aggressive noise reduction and frequency correction",
            highpass_freq=80,
            hum_freq=60,  # Will be detected automatically
            hum_harmonics=[2, 3, 4],  # 120Hz, 180Hz, 240Hz
            hum_q=5.0,
            hum_gain_db=-30.0,
            use_declick=False,  # Disabled - not available in all FFmpeg builds
            use_decrackle=False,  # Disabled - not available in all FFmpeg builds
            noise_reduce_prop=0.9,  # More aggressive
            noise_freq_mask_smooth_hz=500,
            eq_bands={
                250.0: -4.0,   # Cut 250-500Hz by -4dB
                350.0: -4.0,
                500.0: -4.0,
                2500.0: 5.0,   # Shelf boost 2.5kHz+ by +5dB
                4000.0: 5.0,
                8000.0: 2.0,   # Gentle boost at 8kHz +2dB
            },
            compressor_threshold_db=-18.0,
            compressor_ratio=4.0,
            compressor_attack_ms=5.0,
            compressor_release_ms=150.0,
        ),

        ProfileType.PHONE: EnhancementProfile(
            name="phone",
            description="Telephone/lo-fi recording restoration - focus on speech intelligibility",
            highpass_freq=100,
            hum_freq=60,
            hum_harmonics=[],  # Minimal, just fundamental
            hum_q=5.0,
            hum_gain_db=-20.0,
            use_declick=False,
            use_decrackle=False,
            noise_reduce_prop=0.6,  # Moderate
            noise_freq_mask_smooth_hz=500,
            eq_bands={
                200.0: -6.0,   # Cut below 200Hz
                1000.0: 3.0,   # Boost 1-4kHz for speech intelligibility
                2000.0: 4.0,
                3000.0: 4.0,
                4000.0: 3.0,
            },
            compressor_threshold_db=-22.0,
            compressor_ratio=3.0,
            compressor_attack_ms=5.0,
            compressor_release_ms=100.0,
        ),

        ProfileType.CLEAN: EnhancementProfile(
            name="clean",
            description="Minimal processing - only compression and loudness normalization",
            highpass_freq=50,  # Very gentle
            hum_freq=None,  # Skip hum removal
            use_declick=False,
            use_decrackle=False,
            noise_reduce_prop=0.0,  # No noise reduction
            noise_freq_mask_smooth_hz=0,
            eq_bands={},  # No EQ
            compressor_threshold_db=-20.0,
            compressor_ratio=2.0,  # Gentle compression
            compressor_attack_ms=10.0,
            compressor_release_ms=200.0,
        ),

        ProfileType.NONE: EnhancementProfile(
            name="none",
            description="No enhancement - only format conversion and metadata tagging",
            highpass_freq=0,
            hum_freq=None,
            use_declick=False,
            use_decrackle=False,
            noise_reduce_prop=0.0,
            noise_freq_mask_smooth_hz=0,
            eq_bands={},
            compressor_threshold_db=0,
            compressor_ratio=1.0,  # No compression
            compressor_attack_ms=0,
            compressor_release_ms=0,
            loudness_target_lufs=-16.0,  # Still normalize loudness
        ),
    }

    @classmethod
    def get_profile(cls, profile_type: ProfileType) -> EnhancementProfile:
        """
        Get a profile by type

        Args:
            profile_type: Profile type enum

        Returns:
            Enhancement profile configuration

        Raises:
            ProfileError: If profile not found
        """
        if profile_type not in cls.PROFILES:
            raise ProfileError(f"Unknown profile type: {profile_type}")

        return cls.PROFILES[profile_type]

    @classmethod
    def get_profile_by_name(cls, name: str) -> Optional[EnhancementProfile]:
        """
        Get a profile by name string

        Args:
            name: Profile name (case-insensitive)

        Returns:
            Enhancement profile configuration or None for AUTO

        Raises:
            ProfileError: If profile not found (except for AUTO)
        """
        # Special handling for AUTO profile
        if name.lower() == "auto":
            return None  # AUTO needs file analysis, handled separately

        try:
            profile_type = ProfileType(name.lower())
            return cls.get_profile(profile_type)
        except ValueError:
            raise ProfileError(f"Unknown profile name: {name}")

    @classmethod
    def auto_detect(cls, audio_path: Path) -> EnhancementProfile:
        """
        Auto-detect best profile based on audio analysis

        Args:
            audio_path: Path to audio file

        Returns:
            Recommended enhancement profile
        """
        from .utils.audio import detect_audio_profile_heuristics

        try:
            # Detect profile using audio analysis
            detected_name = detect_audio_profile_heuristics(audio_path)
            logger.info(f"Auto-detected profile: {detected_name}")

            # Return the detected profile
            return cls.get_profile_by_name(detected_name)

        except Exception as e:
            logger.warning(f"Auto-detection failed: {e}. Using cassette profile as default.")
            return cls.get_profile(ProfileType.CASSETTE)

    @classmethod
    def list_profiles(cls) -> List[Tuple[str, str]]:
        """
        List all available profiles

        Returns:
            List of (name, description) tuples
        """
        result = []
        for profile in ProfileType:
            if profile == ProfileType.AUTO:
                result.append(("auto", "Automatically detect and apply the best profile"))
            elif profile in cls.PROFILES:
                result.append((profile.value, cls.PROFILES[profile].description))
        return result

    @classmethod
    def detect_hum_frequency(cls, audio_path: Path) -> Optional[int]:
        """
        Detect power line hum frequency (50 or 60 Hz)

        Args:
            audio_path: Path to audio file

        Returns:
            Detected frequency (50 or 60) or None if not detected
        """
        try:
            import numpy as np
            from .utils.audio import load_audio, detect_silence

            # Load first 10 seconds
            audio_data, sample_rate = load_audio(audio_path)
            max_samples = 10 * sample_rate
            if audio_data.shape[1] > max_samples:
                audio_data = audio_data[:, :max_samples]

            # Find silence segments for analysis
            silence_segments = detect_silence(
                audio_data,
                sample_rate,
                threshold_db=-40,
                min_duration=0.5
            )

            if not silence_segments:
                # No silence found, analyze the whole segment
                segment = audio_data
            else:
                # Analyze first silence segment
                start_time, end_time = silence_segments[0]
                start_sample = int(start_time * sample_rate)
                end_sample = int(end_time * sample_rate)
                segment = audio_data[:, start_sample:end_sample]

            # Convert to mono if stereo
            if segment.ndim == 2:
                mono = np.mean(segment, axis=0)
            else:
                mono = segment

            # Compute FFT
            fft = np.fft.rfft(mono)
            freqs = np.fft.rfftfreq(len(mono), 1/sample_rate)
            magnitude = np.abs(fft)

            # Check for peaks at 50Hz and 60Hz
            peak_50 = cls._get_peak_strength(freqs, magnitude, 50, tolerance=2)
            peak_60 = cls._get_peak_strength(freqs, magnitude, 60, tolerance=2)

            logger.debug(f"Hum detection - 50Hz: {peak_50:.2f}, 60Hz: {peak_60:.2f}")

            # Determine which is stronger
            if peak_50 > peak_60 and peak_50 > 0.1:
                logger.info("Detected 50Hz hum (EU/Asia power grid)")
                return 50
            elif peak_60 > peak_50 and peak_60 > 0.1:
                logger.info("Detected 60Hz hum (US/Japan power grid)")
                return 60
            else:
                logger.debug("No significant hum detected")
                return None

        except Exception as e:
            logger.warning(f"Hum detection failed: {e}")
            return None

    @staticmethod
    def _get_peak_strength(freqs, magnitude, target_freq, tolerance=2):
        """Get the strength of a frequency peak"""
        mask = (freqs >= target_freq - tolerance) & (freqs <= target_freq + tolerance)
        if np.any(mask):
            peak_mag = np.max(magnitude[mask])
            # Normalize by average magnitude
            avg_mag = np.mean(magnitude)
            if avg_mag > 0:
                return peak_mag / avg_mag
        return 0.0