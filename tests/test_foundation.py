import logging
import unittest

from app.core.config import Settings, load_settings
from app.core.logging_config import configure_logging, get_logger


class FoundationTests(unittest.TestCase):
    def test_default_settings(self) -> None:
        settings = load_settings()

        self.assertEqual(settings.app_name, "AI Audiobook Maker")
        self.assertEqual(settings.log_level, "INFO")
        self.assertEqual(settings.data_dir, Settings.data_dir)

    def test_logging_helpers(self) -> None:
        configure_logging()

        self.assertIsInstance(get_logger(__name__), logging.Logger)


if __name__ == "__main__":
    unittest.main()
