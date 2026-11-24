"""Job state and JSON persistence for audiobook generation."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
import os
import tempfile
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.book.models import Book
from app.narrator.models import NarratorProfile


class JobState(StrEnum):
    """Lifecycle states for an audiobook job."""

    QUEUED = "QUEUED"
    ANALYZING = "ANALYZING"
    GENERATING = "GENERATING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(BaseModel):
    """A persisted unit of audiobook work."""

    model_config = ConfigDict(use_enum_values=True)

    job_id: str = Field(default_factory=lambda: str(uuid4()))
    state: JobState = JobState.QUEUED
    book: Book
    narrator: NarratorProfile
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    current_chapter: str | None = None
    output: Path | None = None
    error: str | None = None

    @field_validator("job_id")
    @classmethod
    def require_job_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value


class JobManager:
    """Persist and retrieve jobs as individual JSON files."""

    def __init__(self, directory: str | Path = "data/jobs") -> None:
        self._directory = Path(directory)

    def create(
        self,
        book: Book,
        narrator: NarratorProfile,
        job_id: str | None = None,
    ) -> Job:
        """Create and persist a queued job."""
        job = Job(book=book, narrator=narrator, job_id=job_id or str(uuid4()))
        self.save(job)
        return job

    def get(self, job_id: str) -> Job | None:
        """Load a job by ID, returning ``None`` when it is absent."""
        path = self._path_for(job_id)
        if not path.is_file():
            return None
        try:
            return Job.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Could not load job {job_id}: {exc}") from exc

    def save(self, job: Job) -> Job:
        """Persist a job using an atomic file replacement."""
        self._directory.mkdir(parents=True, exist_ok=True)
        destination = self._path_for(job.job_id)
        descriptor, temporary_name = tempfile.mkstemp(
            dir=self._directory, prefix=f".{job.job_id}.", suffix=".tmp"
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                file.write(job.model_dump_json(indent=2))
            os.replace(temporary_name, destination)
        except OSError:
            if os.path.exists(temporary_name):
                os.unlink(temporary_name)
            raise
        return job

    def update(self, job_id: str, **changes: Any) -> Job:
        """Apply validated field changes and persist the job."""
        job = self.get(job_id)
        if job is None:
            raise KeyError(f"Job does not exist: {job_id}")
        updated = job.model_copy(update=changes)
        updated = Job.model_validate(updated)
        return self.save(updated)

    def list(self) -> list[Job]:
        """Load valid jobs in deterministic ID order."""
        if not self._directory.is_dir():
            return []
        jobs = []
        for path in sorted(self._directory.glob("*.json")):
            job = self.get(path.stem)
            if job is not None:
                jobs.append(job)
        return jobs

    def _path_for(self, job_id: str) -> Path:
        if not job_id or Path(job_id).name != job_id or Path(job_id).suffix:
            raise ValueError("job_id must be a simple non-empty filename-safe ID")
        return self._directory / f"{job_id}.json"


__all__ = ["Job", "JobManager", "JobState"]