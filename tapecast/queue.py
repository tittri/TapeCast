"""
Batch queue management system for TapeCast

Simple JSON-based queue for managing multiple processing jobs
with persistence, parallel processing, and resume capability.
"""

import json
import uuid
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any
from enum import Enum
from dataclasses import dataclass, field, asdict
from concurrent.futures import ThreadPoolExecutor, as_completed

from .config import settings
from .utils.logger import get_logger


logger = get_logger(__name__)


class JobStatus(str, Enum):
    """Job status enumeration"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueueJob:
    """Represents a single job in the queue"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    url: str = ""
    profile: str = "auto"
    status: JobStatus = JobStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None
    output_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'QueueJob':
        """Create QueueJob from dictionary"""
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = JobStatus(data['status'])
        return cls(**data)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        data = asdict(self)
        data['status'] = self.status.value
        return data


class QueueManager:
    """
    Manages a persistent job queue using JSON storage

    Features:
    - Persistent storage in JSON file
    - Thread-safe operations
    - Parallel processing support
    - Resume capability for interrupted jobs
    - Job history tracking
    """

    def __init__(self, queue_file: Optional[Path] = None):
        """
        Initialize queue manager

        Args:
            queue_file: Path to queue JSON file (defaults to ~/.tapecast/queue.json)
        """
        if queue_file is None:
            queue_dir = Path.home() / ".tapecast"
            queue_dir.mkdir(parents=True, exist_ok=True)
            self.queue_file = queue_dir / "queue.json"
        else:
            self.queue_file = Path(queue_file)
            self.queue_file.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._load_queue()

    def _load_queue(self) -> None:
        """Load queue from JSON file"""
        if self.queue_file.exists():
            try:
                with open(self.queue_file, 'r') as f:
                    data = json.load(f)
                    self.jobs = [QueueJob.from_dict(job) for job in data.get('jobs', [])]
                    logger.debug(f"Loaded {len(self.jobs)} jobs from {self.queue_file}")
            except Exception as e:
                logger.error(f"Failed to load queue: {e}")
                self.jobs = []
        else:
            self.jobs = []
            logger.debug("Starting with empty queue")

    def _save_queue(self) -> None:
        """Save queue to JSON file"""
        try:
            data = {
                'version': '1.0',
                'updated_at': datetime.now().isoformat(),
                'jobs': [job.to_dict() for job in self.jobs]
            }

            # Write atomically using temp file
            temp_file = self.queue_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                json.dump(data, f, indent=2)

            # Move temp file to actual file (atomic on POSIX)
            temp_file.replace(self.queue_file)

        except Exception as e:
            logger.error(f"Failed to save queue: {e}")
            raise

    def add_job(
        self,
        url: str,
        profile: str = "auto",
        metadata: Optional[Dict[str, Any]] = None
    ) -> QueueJob:
        """
        Add a new job to the queue

        Args:
            url: YouTube URL or local file path to process
            profile: Enhancement profile to use
            metadata: Optional metadata for the job

        Returns:
            Created job
        """
        with self._lock:
            job = QueueJob(
                url=url,
                profile=profile,
                metadata=metadata or {}
            )
            self.jobs.append(job)
            self._save_queue()
            logger.info(f"Added job {job.id}: {url}")
            return job

    def add_batch(
        self,
        urls: List[str],
        profile: str = "auto"
    ) -> List[QueueJob]:
        """
        Add multiple jobs to the queue

        Args:
            urls: List of URLs to process
            profile: Enhancement profile to use

        Returns:
            List of created jobs
        """
        jobs = []
        with self._lock:
            for url in urls:
                job = QueueJob(url=url, profile=profile)
                self.jobs.append(job)
                jobs.append(job)
                logger.info(f"Added job {job.id}: {url}")
            self._save_queue()
        return jobs

    def get_pending_jobs(self) -> List[QueueJob]:
        """Get all pending jobs"""
        with self._lock:
            return [job for job in self.jobs if job.status == JobStatus.PENDING]

    def get_next_pending(self) -> Optional[QueueJob]:
        """
        Get next pending job and mark it as processing

        Returns:
            Next pending job or None if queue is empty
        """
        with self._lock:
            for job in self.jobs:
                if job.status == JobStatus.PENDING:
                    job.status = JobStatus.PROCESSING
                    job.started_at = datetime.now().isoformat()
                    self._save_queue()
                    return job
            return None

    def update_job_status(
        self,
        job_id: str,
        status: JobStatus,
        error_message: Optional[str] = None,
        output_path: Optional[str] = None
    ) -> bool:
        """
        Update job status

        Args:
            job_id: Job ID to update
            status: New status
            error_message: Error message if failed
            output_path: Output file path if completed

        Returns:
            True if job was found and updated
        """
        with self._lock:
            for job in self.jobs:
                if job.id == job_id:
                    job.status = status

                    if status == JobStatus.COMPLETED:
                        job.completed_at = datetime.now().isoformat()
                        if output_path:
                            job.output_path = output_path
                    elif status == JobStatus.FAILED:
                        job.completed_at = datetime.now().isoformat()
                        if error_message:
                            job.error_message = error_message

                    self._save_queue()
                    logger.debug(f"Updated job {job_id}: {status.value}")
                    return True
            return False

    def get_job(self, job_id: str) -> Optional[QueueJob]:
        """Get job by ID"""
        with self._lock:
            for job in self.jobs:
                if job.id == job_id:
                    return job
            return None

    def list_jobs(
        self,
        status: Optional[JobStatus] = None,
        limit: int = 100
    ) -> List[QueueJob]:
        """
        List jobs with optional filtering

        Args:
            status: Filter by status (None for all)
            limit: Maximum number of jobs to return

        Returns:
            List of jobs
        """
        with self._lock:
            jobs = self.jobs if status is None else [
                job for job in self.jobs if job.status == status
            ]
            # Return most recent first
            return sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]

    def clear_completed(self) -> int:
        """
        Clear completed and failed jobs from queue

        Returns:
            Number of jobs removed
        """
        with self._lock:
            original_count = len(self.jobs)
            self.jobs = [
                job for job in self.jobs
                if job.status not in [JobStatus.COMPLETED, JobStatus.FAILED]
            ]
            removed = original_count - len(self.jobs)
            if removed > 0:
                self._save_queue()
                logger.info(f"Cleared {removed} completed/failed jobs")
            return removed

    def cancel_job(self, job_id: str) -> bool:
        """
        Cancel a pending or processing job

        Args:
            job_id: Job ID to cancel

        Returns:
            True if job was cancelled
        """
        with self._lock:
            for job in self.jobs:
                if job.id == job_id and job.status in [JobStatus.PENDING, JobStatus.PROCESSING]:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now().isoformat()
                    self._save_queue()
                    logger.info(f"Cancelled job {job_id}")
                    return True
            return False

    def cancel_all_pending(self) -> int:
        """
        Cancel all pending jobs

        Returns:
            Number of jobs cancelled
        """
        with self._lock:
            cancelled = 0
            for job in self.jobs:
                if job.status == JobStatus.PENDING:
                    job.status = JobStatus.CANCELLED
                    job.completed_at = datetime.now().isoformat()
                    cancelled += 1

            if cancelled > 0:
                self._save_queue()
                logger.info(f"Cancelled {cancelled} pending jobs")

            return cancelled

    def reset_processing_jobs(self) -> int:
        """
        Reset processing jobs back to pending (useful for recovery)

        Returns:
            Number of jobs reset
        """
        with self._lock:
            reset_count = 0
            for job in self.jobs:
                if job.status == JobStatus.PROCESSING:
                    job.status = JobStatus.PENDING
                    job.started_at = None
                    reset_count += 1

            if reset_count > 0:
                self._save_queue()
                logger.info(f"Reset {reset_count} processing jobs to pending")

            return reset_count

    def get_statistics(self) -> Dict[str, int]:
        """
        Get queue statistics

        Returns:
            Dictionary with job counts by status
        """
        with self._lock:
            stats = {
                'total': len(self.jobs),
                'pending': sum(1 for j in self.jobs if j.status == JobStatus.PENDING),
                'processing': sum(1 for j in self.jobs if j.status == JobStatus.PROCESSING),
                'completed': sum(1 for j in self.jobs if j.status == JobStatus.COMPLETED),
                'failed': sum(1 for j in self.jobs if j.status == JobStatus.FAILED),
                'cancelled': sum(1 for j in self.jobs if j.status == JobStatus.CANCELLED),
            }
            return stats

    def process_queue(
        self,
        processor_func,
        max_workers: int = 4,
        stop_on_error: bool = False
    ) -> Dict[str, int]:
        """
        Process all pending jobs in the queue

        Args:
            processor_func: Function to process each job (takes QueueJob, returns success bool)
            max_workers: Maximum parallel workers
            stop_on_error: Stop processing if a job fails

        Returns:
            Dictionary with processing statistics
        """
        # Reset any stuck processing jobs
        self.reset_processing_jobs()

        pending_jobs = self.get_pending_jobs()
        if not pending_jobs:
            logger.info("No pending jobs to process")
            return {'processed': 0, 'succeeded': 0, 'failed': 0}

        logger.info(f"Processing {len(pending_jobs)} jobs with {max_workers} workers")

        succeeded = 0
        failed = 0

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all jobs
            future_to_job = {}

            for _ in range(len(pending_jobs)):
                job = self.get_next_pending()
                if job:
                    future = executor.submit(processor_func, job)
                    future_to_job[future] = job

            # Process completed jobs
            for future in as_completed(future_to_job):
                job = future_to_job[future]

                try:
                    success = future.result()
                    if success:
                        succeeded += 1
                        self.update_job_status(job.id, JobStatus.COMPLETED)
                    else:
                        failed += 1
                        self.update_job_status(job.id, JobStatus.FAILED)
                        if stop_on_error:
                            logger.warning("Stopping due to job failure")
                            executor.shutdown(wait=False)
                            break

                except Exception as e:
                    failed += 1
                    self.update_job_status(
                        job.id,
                        JobStatus.FAILED,
                        error_message=str(e)
                    )
                    logger.error(f"Job {job.id} failed: {e}")
                    if stop_on_error:
                        logger.warning("Stopping due to job error")
                        executor.shutdown(wait=False)
                        break

        logger.info(f"Queue processing complete: {succeeded} succeeded, {failed} failed")

        return {
            'processed': succeeded + failed,
            'succeeded': succeeded,
            'failed': failed
        }