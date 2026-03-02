"""
Logging configuration for TapeCast
"""

import logging
import sys
from pathlib import Path
from typing import Optional
from rich.logging import RichHandler
from rich.console import Console


# Global console for Rich output
console = Console()


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance with the given name

    Args:
        name: Logger name (usually __name__)

    Returns:
        Configured logger instance
    """
    return logging.getLogger(f"tapecast.{name}")


def setup_logging(
    verbose: bool = False,
    log_file: Optional[Path] = None,
    log_level: Optional[str] = None
) -> None:
    """
    Configure global logging for TapeCast

    Args:
        verbose: Enable verbose output
        log_file: Optional file to write logs to
        log_level: Override log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
    """
    from ..config import settings

    # Determine log level
    if log_level:
        level = getattr(logging, log_level.upper())
    elif verbose:
        level = logging.DEBUG
    else:
        level = getattr(logging, settings.log_level)

    # Create root logger for tapecast
    root_logger = logging.getLogger("tapecast")
    root_logger.setLevel(level)

    # Clear any existing handlers
    root_logger.handlers.clear()

    # Console handler with Rich formatting
    console_handler = RichHandler(
        console=console,
        show_time=verbose,
        show_path=verbose,
        rich_tracebacks=True,
        tracebacks_show_locals=verbose,
        markup=True
    )
    console_handler.setLevel(level)

    # Format for console
    console_format = "%(message)s"
    if verbose:
        console_format = "[%(name)s] %(message)s"

    console_handler.setFormatter(logging.Formatter(console_format))
    root_logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Always log everything to file
        file_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        file_handler.setFormatter(logging.Formatter(file_format))
        root_logger.addHandler(file_handler)

    # Configure third-party loggers
    third_party_loggers = [
        "yt_dlp",
        "whisper",
        "httpx",
        "anthropic",
        "google",
        "urllib3",
    ]

    for logger_name in third_party_loggers:
        third_party_logger = logging.getLogger(logger_name)
        # Only show warnings and above for third-party libraries unless in verbose mode
        third_party_logger.setLevel(logging.DEBUG if verbose else logging.WARNING)

    # Suppress specific noisy loggers
    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)
    logging.getLogger("google.auth.transport.requests").setLevel(logging.WARNING)

    # Log startup info
    logger = get_logger("setup")
    logger.debug(f"Logging initialized - Level: {logging.getLevelName(level)}")
    if log_file:
        logger.debug(f"Logging to file: {log_file}")


def log_banner() -> None:
    """Display TapeCast banner"""
    banner = """
[bold cyan]╔══════════════════════════════════════════╗
║                TAPECAST                  ║
║     YouTube to Podcast Enhancement       ║
╚══════════════════════════════════════════╝[/bold cyan]
    """
    console.print(banner)