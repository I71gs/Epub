"""Audiobook generation pipeline orchestration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.book import BookParser
from app.core.logging_config import get_logger
from app.narrator import NarratorRegistry
from app.pipeline.job import Job, JobManager, JobState
from app.tts import E2AAdapter


class AudiobookPipeline:
    """Connect book parsing, narrator selection, jobs, and E2A."""

    _OUTPUT_FORMATS = {"m4b", "mp3"}

    def __init__(
        self,
        parser: BookParser | None = None,
        narrator_registry: NarratorRegistry | None = None,
        job_manager: JobManager | None = None,
        e2a_adapter: E2AAdapter | None = None,
        output_dir: str | Path = "output",
    ) -> None:
        self._parser = parser or BookParser()
        self._narrators = narrator_registry or NarratorRegistry()
        self._jobs = job_manager or JobManager()
        self._e2a = e2a_adapter or E2AAdapter()
        self._output_dir = Path(output_dir)
        self._logger = get_logger(__name__)

    def run(
        self,
        source_path: str | Path,
        narrator_id: str,
        output_format: str = "m4b",
        job_id: str | None = None,
    ) -> Job:
        """Run one book through parsing, narrator selection, and E2A."""
        output_format = output_format.lower().lstrip(".")
        if output_format not in self._OUTPUT_FORMATS:
            raise ValueError("output_format must be m4b or mp3")

        book = self._parser.parse(source_path)
        if not book.chapters:
            raise ValueError("Book must contain at least one chapter")
        narrator_validation = self._narrators.validate(narrator_id)
        if not narrator_validation["ok"]:
            messages = "; ".join(error["message"] for error in narrator_validation["errors"])
            raise ValueError(f"Narrator validation failed: {messages}")
        narrator = self._narrators.get(narrator_id)
        if narrator is None:
            raise ValueError(f"Narrator does not exist: {narrator_id}")

        self._output_dir.mkdir(parents=True, exist_ok=True)
        job = self._jobs.create(book, narrator, job_id=job_id)
        try:
            job = self._jobs.update(job.job_id, state=JobState.ANALYZING)
            job = self._jobs.update(job.job_id, state=JobState.GENERATING)
            request = {
                "input_path": book.source_path,
                "language": book.metadata.language or "eng",
                "voice_path": narrator.reference_path,
                "output_dir": self._output_dir,
                "output_format": output_format,
                "session_id": job.job_id,
            }
            self._logger.info("Generating job %s for narrator %s", job.job_id, narrator.id)
            result = self._e2a.generate(request)
            if not result["ok"]:
                error = self._format_errors(result.get("errors", []))
                return self._jobs.update(job.job_id, state=JobState.FAILED, error=error)
            output = result.get("output_path")
            if not output:
                return self._jobs.update(
                    job.job_id,
                    state=JobState.FAILED,
                    error="E2A completed without an output path",
                )
            return self._jobs.update(
                job.job_id,
                state=JobState.COMPLETED,
                progress=1.0,
                current_chapter=None,
                output=Path(output),
            )
        except Exception as exc:
            self._logger.exception("Audiobook job %s failed", job.job_id)
            return self._jobs.update(job.job_id, state=JobState.FAILED, error=str(exc))

    @staticmethod
    def _format_errors(errors: list[dict[str, Any]]) -> str:
        if not errors:
            return "E2A generation failed"
        return "; ".join(
            f"{error.get('code', 'error')}: {error.get('message', 'unknown error')}"
            for error in errors
        )


__all__ = ["AudiobookPipeline"]