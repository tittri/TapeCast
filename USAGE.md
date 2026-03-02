# TapeCast Usage Guide

## Quick Setup

TapeCast can be used in multiple ways after installation:

### Option 1: Using the launcher script (Recommended)
```bash
./tapecast.sh process "https://youtube.com/watch?v=VIDEO_ID" --profile cassette
```

### Option 2: Activating the virtual environment
```bash
source venv/bin/activate
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --profile cassette
```

### Option 3: Add to your shell configuration
Add this alias to your `~/.zshrc` or `~/.bashrc`:
```bash
alias tapecast="/Users/ismail/Documents/CODE/TapeCast/tapecast.sh"
```
Then you can use:
```bash
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --profile cassette
```

## Common Commands

### Download audio only
```bash
tapecast download "https://youtube.com/watch?v=VIDEO_ID"
```

### Process with different profiles
```bash
# No enhancement (format conversion only)
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --profile none

# Clean podcast quality
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --profile clean

# Retro cassette sound (Note: may have compatibility issues with Python 3.14)
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --profile cassette

# Auto-detect best profile
tapecast process "https://youtube.com/watch?v=VIDEO_ID" --profile auto
```

### Output formats
```bash
# MP3 (default)
tapecast process "URL" --format mp3

# FLAC (lossless)
tapecast process "URL" --format flac

# WAV (uncompressed)
tapecast process "URL" --format wav
```

### Other options
```bash
# Specify output directory
tapecast process "URL" --output ./my-podcasts

# Keep original downloaded file
tapecast process "URL" --keep-original

# Force reprocess existing files
tapecast process "URL" --force

# Dry run (show what would be done)
tapecast process "URL" --dry-run
```

### View available profiles
```bash
tapecast profiles
```

### Show configuration
```bash
tapecast config
```

### Get help
```bash
tapecast --help
tapecast process --help
```

## Note on Python 3.14 Compatibility

You're using Python 3.14.2, which has a compatibility issue with the `pedalboard` audio library.
The following profiles work without issues:
- `none` - No processing
- `clean` - Basic normalization

The retro profiles (`cassette`, `vhs`, `phone`) may encounter errors due to the pedalboard incompatibility.