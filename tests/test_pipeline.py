import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from unittest.mock import Mock

from app.book import BookParser
from app.narrator import NarratorRegistry
from app.pipeline import AudiobookPipeline, JobManager, JobState


class PipelineTests(unittest.TestCase):
    def test_runs_epub_to_completed_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            self._write_epub(source)
            narrator_dir = root / "narrators" / "alice"
            narrator_dir.mkdir(parents=True)
            (narrator_dir / "profile.json").write_text(
                json.dumps({"id": "alice", "name": "Alice", "language": "eng"}),
                encoding="utf-8",
            )
            (narrator_dir / "reference.wav").write_bytes(b"reference")
            output = root / "output" / "book.m4b"
            adapter = Mock()
            adapter.generate.return_value = {"ok": True, "output_path": str(output)}
            pipeline = AudiobookPipeline(
                parser=BookParser(),
                narrator_registry=NarratorRegistry(root / "narrators"),
                job_manager=JobManager(root / "jobs"),
                e2a_adapter=adapter,
                output_dir=root / "output",
            )

            job = pipeline.run(source, "alice", output_format="m4b", job_id="job-1")
            persisted = JobManager(root / "jobs").get("job-1")

        self.assertEqual(job.state, JobState.COMPLETED)
        self.assertEqual(job.output, output)
        self.assertEqual(persisted.state, JobState.COMPLETED)
        adapter.generate.assert_called_once()
        self.assertEqual(adapter.generate.call_args.args[0]["session_id"], "job-1")

    def test_persists_failed_e2a_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            self._write_epub(source)
            narrator_dir = root / "narrators" / "alice"
            narrator_dir.mkdir(parents=True)
            (narrator_dir / "profile.json").write_text(
                json.dumps({"id": "alice", "name": "Alice"}), encoding="utf-8"
            )
            (narrator_dir / "reference.wav").write_bytes(b"reference")
            adapter = Mock()
            adapter.generate.return_value = {
                "ok": False,
                "errors": [{"code": "launch_failed", "message": "E2A unavailable"}],
            }
            job = AudiobookPipeline(
                narrator_registry=NarratorRegistry(root / "narrators"),
                job_manager=JobManager(root / "jobs"),
                e2a_adapter=adapter,
                output_dir=root / "output",
            ).run(source, "alice", job_id="job-2")

        self.assertEqual(job.state, JobState.FAILED)
        self.assertIn("E2A unavailable", job.error)

    @staticmethod
    def _write_epub(path: Path) -> None:
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(
                "META-INF/container.xml",
                '<container><rootfiles><rootfile full-path="content.opf" /></rootfiles></container>',
            )
            archive.writestr(
                "content.opf",
                '<package><metadata xmlns:dc="dc"><dc:title>Book</dc:title><dc:creator>Author</dc:creator></metadata><manifest><item id="chapter" href="chapter.xhtml" media-type="application/xhtml+xml" /></manifest><spine><itemref idref="chapter" /></spine></package>',
            )
            archive.writestr("chapter.xhtml", "<h1>Chapter One</h1><p>Text.</p>")


if __name__ == "__main__":
    unittest.main()