from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.tts.e2a_adapter import E2AAdapter


class FakeProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.stdout = self
        self.stderr = self
        self.lines = iter(["12.50% converting\n", "done\n"])
        self.created_command = None

    def readline(self) -> str:
        return next(self.lines, "")

    def close(self) -> None:
        pass

    def poll(self) -> int:
        return self.returncode

    def wait(self, timeout: float | None = None) -> int:
        return self.returncode

    def terminate(self) -> None:
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9


class E2AAdapterTests(unittest.TestCase):
    def test_validate_rejects_non_ebook(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.png"
            source.touch()
            result = E2AAdapter("app.py").validate(
                {"input_path": source, "output_dir": root, "output_format": "m4b"}
            )

        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["code"], "unsupported_input")

    @patch("app.tts.e2a_adapter.subprocess.Popen")
    def test_generate_captures_streams_and_builds_headless_command(self, popen: object) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            source.touch()
            output = root / "book.m4b"
            fake = FakeProcess()
            popen.return_value = fake

            with patch.object(E2AAdapter, "_find_output", return_value=output):
                result = E2AAdapter("app.py").generate(
                    {
                        "input_path": source,
                        "language": "eng",
                        "output_dir": root,
                        "output_format": "m4b",
                        "session_id": "job-1",
                    }
                )

        command = popen.call_args.args[0]
        self.assertTrue(result["ok"])
        self.assertIn("--headless", command)
        self.assertIn("--session", command)
        self.assertIn("12.50% converting", result["stdout"])
        self.assertEqual(result["progress"], 1.0)

    @patch("app.tts.e2a_adapter.subprocess.Popen")
    def test_resume_reuses_previous_request(self, popen: object) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "book.epub"
            source.touch()
            fake = FakeProcess()
            popen.return_value = fake
            adapter = E2AAdapter("app.py")
            with patch.object(E2AAdapter, "_find_output", return_value=root / "book.m4b"):
                adapter.generate({"input_path": source, "output_dir": root})
                adapter.resume("job-2")

        self.assertEqual(popen.call_args.args[0][-1], "job-2")

    def test_discovery_explicit_entrypoint_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            entrypoint_file = Path(tmp_dir) / "custom_e2a.cmd"
            entrypoint_file.touch()

            with patch.dict("os.environ", {"E2A_ENTRYPOINT": str(entrypoint_file)}, clear=True):
                adapter = E2AAdapter()
                info = adapter.discovery_info

            self.assertEqual(info["source"], "E2A_ENTRYPOINT")
            self.assertEqual(info["resolved_path"], str(entrypoint_file))
            self.assertTrue(info["exists"])
            self.assertTrue(info["is_executable"])
            self.assertEqual(info["e2a_root"], str(Path(tmp_dir)))
            self.assertIn("Resolved E2A path:", info["diagnostics"])


    def test_discovery_e2a_root_env_var(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_path = Path(tmp_dir)
            cmd_file = root_path / "ebook2audiobook.cmd"
            cmd_file.touch()

            with patch.dict("os.environ", {"E2A_ROOT": str(root_path)}, clear=True):
                adapter = E2AAdapter()
                info = adapter.discovery_info

            self.assertEqual(info["source"], "E2A_ROOT")
            self.assertEqual(info["resolved_path"], str(cmd_file))
            self.assertTrue(info["exists"])
            self.assertTrue(info["is_executable"])
            self.assertEqual(info["e2a_root"], str(root_path))

    def test_discovery_path_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            found_file = Path(tmp_dir) / "ebook2audiobook.cmd"
            found_file.touch()

            with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=str(found_file)):
                adapter = E2AAdapter()
                info = adapter.discovery_info

            self.assertEqual(info["source"], "PATH")
            self.assertEqual(info["resolved_path"], str(found_file))
            self.assertTrue(info["exists"])
            self.assertTrue(info["is_executable"])
            self.assertEqual(info["e2a_root"], str(Path(tmp_dir)))

    def test_discovery_missing_e2a(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=None):
            adapter = E2AAdapter()
            info = adapter.discovery_info

        self.assertEqual(info["source"], "PATH")
        self.assertFalse(info["exists"])
        self.assertFalse(info["is_executable"])
        self.assertIsNone(info["e2a_root"])
        self.assertIn("Exists: False", info["diagnostics"])


if __name__ == "__main__":
    unittest.main()