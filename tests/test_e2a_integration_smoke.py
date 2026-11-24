import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.book.models import NarrationPlan, NarrationSegment
from app.narration.compiler import NarrationCompiler
from app.narration.smoke_test import check_e2a_availability, run_smoke_test


class E2AIntegrationSmokeTests(unittest.TestCase):
    def test_check_e2a_availability_missing_executable(self) -> None:
        # Non-existing commands/files should report a blocker
        blocker = check_e2a_availability("non_existent_command_12345.exe")
        self.assertIsNotNone(blocker)
        self.assertIn("not found in the system PATH", blocker)

        blocker_abs = check_e2a_availability("C:/path/to/missing/file.cmd")
        self.assertIsNotNone(blocker_abs)
        self.assertIn("does not exist on disk", blocker_abs)

    def test_check_e2a_availability_explicit_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "custom_e2a.cmd"
            file_path.touch()
            with patch.dict("os.environ", {"E2A_ENTRYPOINT": str(file_path)}):
                blocker = check_e2a_availability()
                self.assertIsNone(blocker)

    def test_check_e2a_availability_e2a_root(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root_dir = Path(tmp_dir)
            cmd_file = root_dir / "ebook2audiobook.cmd"
            cmd_file.touch()
            with patch.dict("os.environ", {"E2A_ROOT": str(root_dir)}, clear=True):
                blocker = check_e2a_availability()
                self.assertIsNone(blocker)

    def test_check_e2a_availability_path_lookup(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            cmd_file = Path(tmp_dir) / "ebook2audiobook.cmd"
            cmd_file.touch()
            with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=str(cmd_file)):
                blocker = check_e2a_availability()
                self.assertIsNone(blocker)

    def test_check_e2a_availability_missing(self) -> None:
        with patch.dict("os.environ", {}, clear=True), patch("shutil.which", return_value=None):
            blocker = check_e2a_availability()
            self.assertIsNotNone(blocker)
            self.assertIn("was not found in the system PATH", blocker)
            self.assertIn("Diagnostics:", blocker)


    @patch("app.narration.smoke_test.check_e2a_availability")
    @patch("app.narration.smoke_test.E2AAdapter")
    @patch("app.narration.smoke_test.wave.open")
    def test_run_smoke_test_mocked_success(
        self, mock_wave_open: MagicMock, mock_adapter_cls: MagicMock, mock_check_avail: MagicMock
    ) -> None:
        # 1. Setup mocks
        mock_check_avail.return_value = None  # Mock E2A as available
        
        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter

        # Mock wave duration calculations
        mock_wav = MagicMock()
        mock_wav.getnframes.return_value = 16000 * 3  # 3 seconds at 16kHz
        mock_wav.getframerate.return_value = 16000
        mock_wave_open.return_value.__enter__.return_value = mock_wav

        # Mock adapter generate response
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_file = Path(tmp_dir) / "output.wav"
            out_file.write_bytes(b"mock audio wav data")
            
            mock_adapter.generate.return_value = {
                "ok": True,
                "output_path": str(out_file.resolve()),
            }

            # 2. Run test
            with patch("app.narration.smoke_test.tempfile.mkdtemp", return_value=tmp_dir):
                res = run_smoke_test()

        # 3. Assertions
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIsNone(res["blocker"])
        self.assertIsNotNone(res["generated_file_path"])
        self.assertEqual(res["duration"], 3.0)
        self.assertEqual(res["size"], len(b"mock audio wav data"))

    @patch("app.narration.smoke_test.check_e2a_availability")
    @patch("app.narration.smoke_test.E2AAdapter")
    def test_run_smoke_test_mocked_failure(
        self, mock_adapter_cls: MagicMock, mock_check_avail: MagicMock
    ) -> None:
        mock_check_avail.return_value = None
        
        mock_adapter = MagicMock()
        mock_adapter_cls.return_value = mock_adapter
        mock_adapter.generate.return_value = {
            "ok": False,
            "errors": [{"code": "some_error", "message": "Failed generation"}],
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            with patch("app.narration.smoke_test.tempfile.mkdtemp", return_value=tmp_dir):
                res = run_smoke_test()

        self.assertEqual(res["status"], "FAILED")
        self.assertIn("Failed generation", res["blocker"])
        self.assertIsNone(res["generated_file_path"])


if __name__ == "__main__":
    unittest.main()
