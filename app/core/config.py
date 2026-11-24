"""Application configuration loaded from environment variables."""

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    """Runtime settings for the application foundation."""

    app_name: str = "AI Audiobook Maker"
    log_level: str = "INFO"
    data_dir: Path = Path("data")
    narrators_dir: Path = Path("narrators")
    output_dir: Path = Path("output")


def load_settings() -> Settings:
    """Load settings, applying optional environment variable overrides."""
    return Settings(
        app_name=os.getenv("AUDIOBOOK_APP_NAME", Settings.app_name),
        log_level=os.getenv("AUDIOBOOK_LOG_LEVEL", Settings.log_level).upper(),
        data_dir=Path(os.getenv("AUDIOBOOK_DATA_DIR", str(Settings.data_dir))),
        narrators_dir=Path(
            os.getenv("AUDIOBOOK_NARRATORS_DIR", str(Settings.narrators_dir))
        ),
        output_dir=Path(os.getenv("AUDIOBOOK_OUTPUT_DIR", str(Settings.output_dir))),
    )
