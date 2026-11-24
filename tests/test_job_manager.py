from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError

from app.book import Book
from app.narrator import NarratorProfile
from app.pipeline import Job, JobManager, JobState


class JobManagerTests(unittest.TestCase):
    def _book(self) -> Book:
        return Book(id="book-1", source_path="book.epub", title="Book", author="Author")

    def _narrator(self) -> NarratorProfile:
        return NarratorProfile(id="alice", name="Alice")

    def test_create_update_and_reload_json_state(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = JobManager(directory)
            created = manager.create(self._book(), self._narrator(), job_id="job-1")
            updated = manager.update(
                created.job_id,
                state=JobState.GENERATING,
                progress=0.5,
                current_chapter="Opening",
                output=Path("output/book.m4b"),
            )
            loaded = JobManager(directory).get("job-1")

            self.assertTrue((Path(directory) / "job-1.json").is_file())

        self.assertEqual(created.state, JobState.QUEUED)
        self.assertEqual(updated.state, JobState.GENERATING)
        self.assertEqual(loaded.progress, 0.5)
        self.assertEqual(loaded.current_chapter, "Opening")
        self.assertEqual(loaded.output, Path("output/book.m4b"))

    def test_list_and_missing_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            manager = JobManager(directory)
            manager.create(self._book(), self._narrator(), job_id="job-2")

            self.assertEqual([job.job_id for job in manager.list()], ["job-2"])
            self.assertIsNone(manager.get("missing"))

    def test_progress_and_id_are_validated(self) -> None:
        with self.assertRaises(ValidationError):
            Job(job_id=" ", book=self._book(), narrator=self._narrator())
        with self.assertRaises(ValidationError):
            Job(book=self._book(), narrator=self._narrator(), progress=1.1)


if __name__ == "__main__":
    unittest.main()