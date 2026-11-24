from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from app import __main__


class CliTests(unittest.TestCase):
    def test_cli_imports_and_help(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "app", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("generate", result.stdout)

    def test_generate_reports_adapter_validation_errors(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            with patch.object(
                __main__.E2AAdapter,
                "generate",
                return_value={
                    "ok": False,
                    "errors": [{"code": "unsupported_input", "message": "input_path must be PDF or EPUB"}],
                },
            ) as generate:
                with patch.object(
                    sys,
                    "argv",
                    ["app", "generate", "book.txt", "--output-dir", str(output_dir)],
                ):
                    with redirect_stdout(StringIO()):
                        result = __main__.main()

        self.assertEqual(result, 1)
        generate.assert_called_once()


if __name__ == "__main__":
    unittest.main()