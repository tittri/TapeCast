"""
Progress tracking utilities for TapeCast
"""

from pathlib import Path
from typing import Optional, Callable, Any
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeRemainingColumn,
    TimeElapsedColumn,
    MofNCompleteColumn,
)
from rich.console import Console
from rich.table import Table
from contextlib import contextmanager


console = Console()


class ProgressTracker:
    """Track progress for multi-stage operations"""

    def __init__(self, total_stages: int = 1, description: str = "Processing"):
        self.total_stages = total_stages
        self.current_stage = 0
        self.description = description
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            TimeElapsedColumn(),
            console=console,
            transient=False
        )
        self.task_id = None
        self.stage_task_id = None

    def __enter__(self):
        self.progress.__enter__()
        self.task_id = self.progress.add_task(
            self.description,
            total=self.total_stages
        )
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.progress.__exit__(exc_type, exc_val, exc_tb)

    def start_stage(self, stage_num: int, description: str, total: int = 100) -> None:
        """Start a new stage of processing"""
        self.current_stage = stage_num
        if self.stage_task_id is not None:
            self.progress.stop_task(self.stage_task_id)

        self.stage_task_id = self.progress.add_task(
            f"  {description}",
            total=total
        )
        self.progress.update(
            self.task_id,
            completed=stage_num - 1,
            description=f"{self.description} - Stage {stage_num}/{self.total_stages}"
        )

    def update_stage(self, completed: float, description: Optional[str] = None) -> None:
        """Update current stage progress"""
        if self.stage_task_id is not None:
            updates = {"completed": completed}
            if description:
                updates["description"] = f"  {description}"
            self.progress.update(self.stage_task_id, **updates)

    def complete_stage(self) -> None:
        """Mark current stage as complete"""
        if self.stage_task_id is not None:
            self.progress.update(self.stage_task_id, completed=100)
            self.progress.stop_task(self.stage_task_id)
            self.stage_task_id = None
        self.progress.update(self.task_id, completed=self.current_stage)

    def complete(self) -> None:
        """Mark all processing as complete"""
        if self.stage_task_id is not None:
            self.progress.stop_task(self.stage_task_id)
        self.progress.update(self.task_id, completed=self.total_stages)


class DownloadProgressCallback:
    """Progress callback for yt-dlp downloads"""

    def __init__(self, progress_bar: Optional[Progress] = None, task_id: Optional[int] = None):
        self.progress_bar = progress_bar
        self.task_id = task_id
        self.last_percentage = 0

    def __call__(self, d: dict) -> None:
        """Handle progress updates from yt-dlp"""
        if not self.progress_bar or self.task_id is None:
            return

        if d['status'] == 'downloading':
            # Extract percentage
            if '_percent_str' in d:
                percent_str = d['_percent_str'].strip('%')
                try:
                    percentage = float(percent_str)
                    if percentage != self.last_percentage:
                        self.progress_bar.update(
                            self.task_id,
                            completed=percentage,
                            description=f"Downloading: {d.get('filename', 'Unknown')}"
                        )
                        self.last_percentage = percentage
                except ValueError:
                    pass

            # Update with speed and ETA if available
            if 'speed' in d and '_eta_str' in d:
                speed = d['speed']
                eta = d['_eta_str']
                if speed:
                    speed_mb = speed / (1024 * 1024)
                    self.progress_bar.update(
                        self.task_id,
                        description=f"Downloading ({speed_mb:.1f} MB/s, ETA: {eta})"
                    )

        elif d['status'] == 'finished':
            self.progress_bar.update(
                self.task_id,
                completed=100,
                description="Download complete"
            )

        elif d['status'] == 'error':
            self.progress_bar.update(
                self.task_id,
                description=f"[red]Download failed[/red]"
            )


@contextmanager
def progress_context(description: str = "Processing", total: int = 100):
    """Simple context manager for progress bars"""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False
    ) as progress:
        task_id = progress.add_task(description, total=total)
        yield progress, task_id


def create_summary_table(title: str, data: list[dict[str, Any]]) -> Table:
    """
    Create a Rich table for displaying summary information

    Args:
        title: Table title
        data: List of dictionaries with data to display

    Returns:
        Formatted Rich table
    """
    if not data:
        return Table(title=title, show_header=False)

    # Create table with title
    table = Table(title=title, show_header=True, header_style="bold cyan")

    # Add columns based on first item's keys
    for key in data[0].keys():
        # Convert snake_case to Title Case
        column_name = key.replace('_', ' ').title()
        table.add_column(column_name)

    # Add rows
    for item in data:
        table.add_row(*[str(v) for v in item.values()])

    return table


def display_file_list(files: list[Path], title: str = "Files") -> None:
    """Display a formatted list of files"""
    table = Table(title=title, show_header=True)
    table.add_column("Index", style="dim", width=6)
    table.add_column("Filename")
    table.add_column("Size", justify="right")

    for idx, file in enumerate(files, 1):
        if file.exists():
            size = file.stat().st_size
            size_str = format_file_size(size)
        else:
            size_str = "N/A"

        table.add_row(
            str(idx),
            file.name,
            size_str
        )

    console.print(table)


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def format_duration(seconds: float) -> str:
    """Format duration in seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"