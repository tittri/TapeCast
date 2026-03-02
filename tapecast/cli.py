"""
TapeCast CLI interface using Typer
"""

import sys
from pathlib import Path
from typing import Optional
from datetime import datetime
import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from .config import settings, get_settings
from .downloader import YouTubeDownloader
from .profiles import ProfileManager, ProfileType
from .utils.logger import setup_logging, log_banner
from .exceptions import TapeCastError
from . import __version__


# Create Typer app
app = typer.Typer(
    name="tapecast",
    help="Transform YouTube videos into retro-styled podcast episodes",
    add_completion=False,
    rich_markup_mode="rich",
    pretty_exceptions_show_locals=False,
)

# Console for Rich output
console = Console()


@app.callback()
def callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    version: bool = typer.Option(False, "--version", help="Show version and exit"),
):
    """TapeCast - YouTube to Podcast Audio Enhancement CLI"""
    if version:
        console.print(f"TapeCast v{__version__}")
        raise typer.Exit()

    # Setup logging
    setup_logging(verbose=verbose)


@app.command()
def download(
    url: str = typer.Argument(..., help="YouTube video/playlist URL or local file path"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output directory for downloaded files"
    ),
    keep_original: bool = typer.Option(
        False, "--keep-original", "-k",
        help="Keep original format (don't convert to WAV)"
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="Force re-download even if file exists"
    ),
):
    """Download audio from YouTube video or playlist"""
    try:
        # Setup
        if output_dir:
            settings.downloads_dir = output_dir
        settings.setup_directories()

        # Show banner
        log_banner()
        console.print(f"\n[cyan]Downloading from:[/cyan] {url}")

        # Create downloader
        downloader = YouTubeDownloader(output_dir=settings.downloads_dir)

        # Download with progress
        with Progress(console=console) as progress:
            task_id = progress.add_task("Downloading...", total=100)

            results = downloader.download(
                url=url,
                progress_bar=progress,
                task_id=task_id,
                keep_original=keep_original,
                force=force,
            )

        # Show results
        console.print("\n[green]Download complete![/green]")

        success_count = sum(1 for r in results if r.is_success)
        total_count = len(results)

        if total_count == 1:
            result = results[0]
            if result.is_success:
                console.print(f"  File: {result.file_path}")
                console.print(f"  Duration: {result.metadata.get('duration', 0)} seconds")
            else:
                console.print(f"[red]Error: {result.error}[/red]")
        else:
            console.print(f"  Downloaded: {success_count}/{total_count} files")

            # List successful downloads
            if success_count > 0:
                console.print("\n[green]Successful downloads:[/green]")
                for r in results:
                    if r.is_success:
                        console.print(f"  ✓ {r.file_path.name}")

            # List failed downloads
            failed = [r for r in results if not r.is_success]
            if failed:
                console.print("\n[red]Failed downloads:[/red]")
                for r in failed:
                    console.print(f"  ✗ Index {r.playlist_index}: {r.error}")

    except TapeCastError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        if settings.log_level == "DEBUG":
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def profiles():
    """List available audio enhancement profiles"""
    log_banner()
    console.print("\n[bold cyan]Available Enhancement Profiles[/bold cyan]\n")

    # Create table
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Profile", style="green", width=12)
    table.add_column("Description", width=60)

    # Add profiles
    for name, description in ProfileManager.list_profiles():
        table.add_row(name, description)

    console.print(table)
    console.print("\n[dim]Use --profile/-p option to select a profile when processing[/dim]")


@app.command()
def info(
    url: str = typer.Argument(..., help="YouTube video URL or local file path"),
):
    """Show metadata for a YouTube video or local file"""
    try:
        log_banner()
        console.print(f"\n[cyan]Getting info for:[/cyan] {url}")

        # Check if it's a local file
        local_path = Path(url)
        if local_path.exists() and local_path.is_file():
            # Get info from local file
            from .utils.ffmpeg import FFmpegWrapper
            ffmpeg = FFmpegWrapper()
            info = ffmpeg.get_audio_info(local_path)

            console.print("\n[bold]Local File Information[/bold]")
            console.print(f"  Filename: {local_path.name}")
            console.print(f"  Duration: {info['duration_str']}")
            console.print(f"  Format: {info['format']}")
            console.print(f"  Codec: {info['codec']}")
            console.print(f"  Sample Rate: {info['sample_rate']} Hz")
            console.print(f"  Channels: {info['channels']}")
            console.print(f"  Bitrate: {info['bitrate'] // 1000} kbps")

        else:
            # Get info from YouTube
            import yt_dlp

            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'extract_flat': False,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)

            console.print("\n[bold]YouTube Video Information[/bold]")
            console.print(f"  Title: {info.get('title', 'Unknown')}")
            console.print(f"  Uploader: {info.get('uploader', 'Unknown')}")
            console.print(f"  Duration: {info.get('duration', 0)} seconds")
            console.print(f"  Upload Date: {info.get('upload_date', 'Unknown')}")
            console.print(f"  Views: {info.get('view_count', 0):,}")

            # Description (truncated)
            description = info.get('description', '')
            if description:
                lines = description.split('\n')[:3]
                console.print(f"\n[bold]Description:[/bold]")
                for line in lines:
                    if len(line) > 80:
                        line = line[:80] + "..."
                    console.print(f"  {line}")
                if len(description.split('\n')) > 3:
                    console.print("  [dim]...[/dim]")

    except Exception as e:
        console.print(f"[red]Error getting info:[/red] {e}")
        raise typer.Exit(1)


@app.command()
def init():
    """Initialize a new TapeCast project with template configuration files"""
    log_banner()
    console.print("\n[cyan]Initializing TapeCast project...[/cyan]")

    # Create podcast.yaml template
    podcast_yaml = Path("podcast.yaml")
    if podcast_yaml.exists():
        if not typer.confirm(f"\n{podcast_yaml} already exists. Overwrite?"):
            console.print("[yellow]Initialization cancelled[/yellow]")
            raise typer.Exit()

    podcast_template = """# TapeCast Podcast Configuration
# This file is used when publishing to podcast RSS feed

podcast:
  title: "My Restored Podcast"
  description: "Classic recordings restored and enhanced with TapeCast"
  author: "Your Name"
  email: "your.email@example.com"
  language: "en"
  category: "History"
  subcategory: "Documentary"
  image: "./cover-art.jpg"  # Path to podcast cover art (minimum 1400x1400)
  website: "https://example.com"
  explicit: false

hosting:
  # Base URL where audio files will be hosted (for generating enclosure URLs)
  base_url: "https://example.com/episodes/"

# Feed settings
feed:
  max_episodes: 100  # Maximum number of episodes to include in feed
  copyright: "© 2024 Your Name"
  iTunes_owner: "Your Name"
  iTunes_email: "your.email@example.com"
"""

    with open(podcast_yaml, 'w') as f:
        f.write(podcast_template)

    console.print(f"[green]✓[/green] Created {podcast_yaml}")

    # Create .env file if it doesn't exist
    env_file = Path(".env")
    if not env_file.exists():
        env_example = Path(".env.example")
        if env_example.exists():
            import shutil
            shutil.copy2(".env.example", ".env")
            console.print(f"[green]✓[/green] Created .env from .env.example")
        else:
            # Create basic .env
            with open(".env", 'w') as f:
                f.write("# TapeCast Environment Variables\n")
                f.write("# Add your API keys here\n")
                f.write("# ANTHROPIC_API_KEY=sk-ant-...\n")
                f.write("# GOOGLE_CLIENT_ID=...\n")
            console.print(f"[green]✓[/green] Created .env")

    # Create output directories
    settings.setup_directories()
    console.print(f"[green]✓[/green] Created output directories")

    console.print("\n[green]Initialization complete![/green]")
    console.print("\nNext steps:")
    console.print("  1. Edit podcast.yaml with your podcast information")
    console.print("  2. Add API keys to .env file (optional)")
    console.print("  3. Run: tapecast download <youtube-url>")
    console.print("  4. Run: tapecast process <youtube-url> --profile cassette")


@app.command()
def config():
    """Show current configuration"""
    log_banner()
    console.print("\n[bold cyan]Current Configuration[/bold cyan]\n")

    config_dict = settings.to_dict()

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("Setting", style="green", width=30)
    table.add_column("Value", width=50)

    for key, value in config_dict.items():
        # Format paths
        if isinstance(value, Path):
            value = str(value)
        # Hide sensitive values
        if "api_key" in key.lower() or "secret" in key.lower():
            if value:
                value = "***" + str(value)[-4:] if len(str(value)) > 4 else "***"
            else:
                value = "[dim]Not set[/dim]"

        table.add_row(key.replace('_', ' ').title(), str(value))

    console.print(table)


@app.command()
def process(
    input_url: str = typer.Argument(..., help="YouTube URL or local file to process"),
    output_dir: Optional[Path] = typer.Option(
        None, "--output", "-o",
        help="Output directory for processed files"
    ),
    format: str = typer.Option(
        "mp3", "--format", "-f",
        help="Output format: mp3, flac, wav, opus, m4a"
    ),
    bitrate: str = typer.Option(
        "192k", "--bitrate", "-b",
        help="Audio bitrate (for lossy formats)"
    ),
    profile: str = typer.Option(
        "auto", "--profile", "-p",
        help="Enhancement profile: auto, cassette, vhs, phone, clean, none"
    ),
    loudness: float = typer.Option(
        -16.0, "--loudness", "-l",
        help="Target loudness in LUFS"
    ),
    ai_metadata: bool = typer.Option(
        False, "--ai-metadata",
        help="Use AI to generate enhanced metadata"
    ),
    whisper_model: str = typer.Option(
        "small", "--whisper-model",
        help="Whisper model size: tiny, base, small, medium, large"
    ),
    keep_original: bool = typer.Option(
        False, "--keep-original",
        help="Keep unprocessed downloaded audio"
    ),
    force: bool = typer.Option(
        False, "--force",
        help="Reprocess files even if output exists"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run",
        help="Show what would be done without processing"
    ),
):
    """Process YouTube video/playlist into podcast episode(s)"""
    from .enhancer import AudioEnhancer
    from .metadata import MetadataExtractor, EpisodeMetadata
    from .utils.progress import ProgressTracker

    try:
        # Setup
        if output_dir:
            settings.output_dir = output_dir
            settings.processed_dir = output_dir / "processed"
            settings.metadata_dir = output_dir / "metadata"
            settings.thumbnails_dir = output_dir / "thumbnails"
        settings.setup_directories()

        # Show banner
        log_banner()
        console.print(f"\n[cyan]Processing:[/cyan] {input_url}")

        # Check if it's a local file
        local_path = Path(input_url)
        if local_path.exists() and local_path.is_file():
            # Process local file
            console.print("[yellow]Processing local file[/yellow]")
            download_results = []
            audio_files = [local_path]
        else:
            # Download from YouTube
            console.print("\n[bold]Step 1: Downloading audio[/bold]")
            downloader = YouTubeDownloader(output_dir=settings.downloads_dir)

            with Progress(console=console) as progress:
                task_id = progress.add_task("Downloading...", total=100)
                download_results = downloader.download(
                    url=input_url,
                    progress_bar=progress,
                    task_id=task_id,
                    keep_original=keep_original,
                    force=force,
                )

            # Get successfully downloaded files
            audio_files = [r.file_path for r in download_results if r.is_success]

            if not audio_files:
                console.print("[red]No files downloaded successfully[/red]")
                raise typer.Exit(1)

        if dry_run:
            # Show what would be done
            console.print("\n[yellow]Dry run mode - no files will be processed[/yellow]")
            console.print(f"Would process {len(audio_files)} file(s):")
            for f in audio_files:
                console.print(f"  - {f.name}")
            console.print(f"Profile: {profile}")
            console.print(f"Output format: {format}")
            console.print(f"Target loudness: {loudness} LUFS")
            if ai_metadata:
                console.print("AI metadata enhancement: Enabled")
            raise typer.Exit()

        # Check if using AUTO profile
        is_auto = profile.lower() == "auto"

        # Get profile (returns None for AUTO)
        profile_obj = ProfileManager.get_profile_by_name(profile)

        # Process each file
        if is_auto:
            console.print(f"\n[bold]Step 2: Enhancing audio with auto-detected profiles[/bold]")
        else:
            console.print(f"\n[bold]Step 2: Enhancing audio with '{profile}' profile[/bold]")

        enhancer = AudioEnhancer()
        metadata_extractor = MetadataExtractor()
        processed_files = []

        for idx, audio_file in enumerate(audio_files, 1):
            if len(audio_files) > 1:
                console.print(f"\n[dim]Processing {idx}/{len(audio_files)}: {audio_file.name}[/dim]")

            # Auto-detect profile if needed
            if is_auto:
                console.print(f"[dim]Auto-detecting best profile for {audio_file.name}...[/dim]")
                profile_obj = ProfileManager.auto_detect(audio_file)
                console.print(f"[cyan]Using profile: {profile_obj.name}[/cyan]")

            # Get metadata first to extract the original title
            if download_results and idx <= len(download_results):
                download_metadata = download_results[idx-1].metadata
                # Use the original title from YouTube for the output filename
                original_title = download_metadata.get('title', audio_file.stem)
            else:
                # Local file - create basic metadata
                download_metadata = {
                    'title': audio_file.stem,
                    'description': f"Local file: {audio_file.name}",
                    'is_local_file': True,
                }
                original_title = audio_file.stem

            # Sanitize the title for use as a filename
            import re
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', original_title)
            safe_title = safe_title.strip()

            # Check if this is part of a playlist and create subfolder if needed
            if download_results and download_results[0].playlist_title:
                # Sanitize playlist title for folder name
                playlist_folder = re.sub(r'[<>:"/\\|?*]', '_', download_results[0].playlist_title)
                playlist_folder = playlist_folder.strip()
                output_dir = settings.processed_dir / playlist_folder
                output_dir.mkdir(parents=True, exist_ok=True)
            else:
                output_dir = settings.processed_dir

            # Generate output filename with _tapecasted suffix
            output_name = f"{safe_title}_tapecasted.{format}"
            output_path = output_dir / output_name

            # Create progress tracker
            with ProgressTracker(
                total_stages=3,
                description=f"Enhancing {audio_file.name}"
            ) as tracker:
                # Enhance audio
                enhanced_path = enhancer.enhance(
                    input_path=audio_file,
                    output_path=output_path,
                    profile=profile_obj,
                    target_format=format,
                    target_bitrate=bitrate,
                    target_loudness=loudness,
                    progress_tracker=tracker,
                    force=force,
                )

            processed_files.append(enhanced_path)

            # Extract metadata
            console.print(f"[dim]Extracting metadata...[/dim]")

            metadata = metadata_extractor.extract_from_download(
                download_metadata,
                enhanced_path,
                playlist_index=idx if len(audio_files) > 1 else None
            )

            # Update processing metadata
            # Use the actual profile that was used (important for AUTO)
            metadata.profile_used = profile_obj.name if profile_obj else profile
            metadata.format = format
            metadata.bitrate = bitrate
            metadata.loudness_lufs = loudness
            metadata.processed_date = datetime.now().isoformat()

            # Download and process thumbnail
            if metadata.thumbnail_url:
                console.print(f"[dim]Downloading thumbnail...[/dim]")
                thumbnail_path = settings.thumbnails_dir / f"{audio_file.stem}.jpg"
                square_thumb = metadata_extractor.download_thumbnail(
                    metadata.thumbnail_url,
                    thumbnail_path,
                    make_square=True
                )

                # Tag audio file
                if square_thumb:
                    console.print(f"[dim]Tagging audio file...[/dim]")
                    metadata_extractor.tag_audio_file(
                        enhanced_path,
                        metadata,
                        cover_art_path=square_thumb
                    )
            else:
                # Tag without cover art
                metadata_extractor.tag_audio_file(enhanced_path, metadata)

            # Save metadata
            metadata_path = settings.metadata_dir / f"{audio_file.stem}.json"
            metadata.save(metadata_path)

            console.print(f"  [green]✓[/green] {enhanced_path.name}")

            # Clean up original if not keeping
            if not keep_original and not audio_file.name.startswith(str(settings.downloads_dir)):
                try:
                    audio_file.unlink()
                    console.print(f"  [dim]Removed original: {audio_file.name}[/dim]")
                except:
                    pass

        # Show summary
        console.print(f"\n[green]✓ Processing complete![/green]")
        console.print(f"  Processed {len(processed_files)} file(s)")

        # Show correct output directory
        if download_results and download_results[0].playlist_title:
            import re
            playlist_folder = re.sub(r'[<>:"/\\|?*]', '_', download_results[0].playlist_title)
            playlist_folder = playlist_folder.strip()
            console.print(f"  Output directory: {settings.processed_dir / playlist_folder}")
        else:
            console.print(f"  Output directory: {settings.processed_dir}")

        if ai_metadata:
            console.print("\n[yellow]Note: AI metadata enhancement is not yet implemented[/yellow]")
            console.print("[yellow]Files have been processed with basic metadata only[/yellow]")

    except TapeCastError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Processing interrupted by user[/yellow]")
        raise typer.Exit(130)
    except (typer.Exit, SystemExit):
        # Re-raise exit codes without catching them as errors
        raise
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        console.print_exception()  # Always show traceback for debugging
        raise typer.Exit(1)


if __name__ == "__main__":
    app()