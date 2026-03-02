# TapeCast 📼

Transform YouTube videos into retro-styled podcast episodes with AI-powered audio enhancement and metadata enrichment.

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-alpha-orange)

## Features

- 🎵 **Download audio** from YouTube videos and playlists
- 🎛️ **Retro audio profiles**: Cassette, VHS, Phone, Clean
- 🤖 **AI-powered metadata** using Whisper transcription and Claude
- 📻 **Podcast publishing** to RSS feeds and YouTube
- 🎨 **Smart audio enhancement** with three-stage processing pipeline
- 📊 **Batch processing** for entire playlists

## Audio Enhancement Profiles

TapeCast includes carefully tuned profiles to give your audio that authentic retro feel:

- **Cassette** 📼 - Warm analog tape sound with light enhancement
- **VHS** 📹 - VHS tape restoration with aggressive noise reduction
- **Phone** ☎️ - Telephone/lo-fi recording with speech focus
- **Clean** 🎧 - Professional podcast quality with minimal processing
- **Auto** 🔍 - Automatically detect and apply the best profile
- **None** ⚡ - No enhancement, just format conversion

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg installed on your system
- (Optional) Anthropic API key for AI features
- (Optional) Google API credentials for YouTube publishing

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/tapecast.git
cd tapecast

# Install with pip
pip install -e .

# Or install with all optional dependencies
pip install -e ".[all]"

# Or use uv (recommended)
uv pip install -e .
```

### Basic Usage

```bash
# Initialize project
tapecast init

# List available audio profiles
tapecast profiles

# Download audio from YouTube
tapecast download "https://youtube.com/watch?v=VIDEO_ID"

# Download entire playlist
tapecast download "https://youtube.com/playlist?list=PLAYLIST_ID"

# Get video information
tapecast info "https://youtube.com/watch?v=VIDEO_ID"

# Process with cassette profile (coming soon)
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --profile cassette

# Process with AI metadata enhancement (coming soon)
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --ai-metadata
```

### Configuration

Create a `.env` file with your API keys:

```env
# For AI metadata enhancement
ANTHROPIC_API_KEY=sk-ant-...

# For YouTube publishing
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...

# Optional: Override defaults
TAPECAST_OUTPUT_DIR=./output
TAPECAST_DEFAULT_PROFILE=cassette
TAPECAST_LOUDNESS=-16.0
```

## Project Structure

```
tapecast/
├── cli.py              # CLI interface using Typer
├── config.py           # Configuration management
├── downloader.py       # YouTube download functionality
├── enhancer.py         # Audio enhancement pipeline
├── profiles.py         # Audio enhancement profiles
├── metadata.py         # Metadata extraction and AI enrichment
├── publisher.py        # Publishing to YouTube/RSS
└── utils/
    ├── ffmpeg.py       # FFmpeg wrapper
    ├── audio.py        # Audio processing utilities
    ├── progress.py     # Progress tracking
    └── logger.py       # Logging configuration
```

## Development Status

TapeCast is currently in active development. Completed features:

- ✅ Project scaffolding and configuration
- ✅ YouTube downloading (single videos and playlists)
- ✅ Audio enhancement profiles
- ✅ FFmpeg integration
- ✅ Basic CLI commands
- 🚧 Audio enhancement pipeline (in progress)
- 🚧 Metadata extraction
- 🚧 AI metadata enrichment
- 🚧 Podcast RSS publishing
- 🚧 YouTube publishing

## Three-Stage Audio Processing Pipeline

TapeCast uses a sophisticated three-stage pipeline for audio enhancement:

### Stage 1: FFmpeg Preprocessing
- High-pass filtering to remove rumble
- Hum removal (50/60Hz and harmonics)
- De-click and de-crackle filters

### Stage 2: Python Processing
- Spectral noise reduction (using `noisereduce`)
- EQ correction with `pedalboard`
- Dynamic compression

### Stage 3: Final Processing
- Two-pass loudness normalization
- Output encoding to target format

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues.

### Development Setup

```bash
# Install development dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Run linting
ruff check tapecast tests

# Format code
black tapecast tests
```

## License

MIT License - see LICENSE file for details.

## Acknowledgments

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for YouTube downloading
- [pedalboard](https://github.com/spotify/pedalboard) by Spotify for audio processing
- [FFmpeg](https://ffmpeg.org/) for audio/video manipulation
- [OpenAI Whisper](https://github.com/openai/whisper) for transcription
- [Anthropic Claude](https://www.anthropic.com/) for AI metadata generation

## Roadmap

- [ ] Complete audio enhancement pipeline
- [ ] Add AI metadata features
- [ ] Implement RSS podcast publishing
- [ ] Add YouTube upload functionality
- [ ] Create web interface (future)
- [ ] Add Docker support
- [ ] Support more audio sources (Vimeo, SoundCloud, etc.)

## Support

For questions, issues, or feature requests, please open an issue on GitHub.

---

**Note:** TapeCast is designed for processing content you own or have permission to use. Please respect copyright and content creators' rights.