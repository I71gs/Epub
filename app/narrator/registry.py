"""Filesystem discovery for narrator profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.core.logging_config import get_logger
from app.narrator.models import NarratorProfile


class NarratorRegistry:
    """Discover narrator profiles from ``<root>/<id>/`` directories."""

    def __init__(self, root: str | Path = "narrators") -> None:
        self._root = Path(root)
        self._logger = get_logger(__name__)

    def discover(self) -> list[NarratorProfile]:
        """Return all valid profiles found below the registry root."""
        if not self._root.is_dir():
            return []
        profiles = []
        for directory in sorted(self._root.iterdir(), key=lambda path: path.name):
            if directory.is_dir():
                profile, errors = self._load(directory)
                if profile is not None:
                    profiles.append(profile)
                elif errors:
                    self._logger.warning("Skipping narrator %s: %s", directory.name, errors)
        return profiles

    def get(self, narrator_id: str) -> NarratorProfile | None:
        """Return a valid profile by ID, or ``None`` when it is unavailable."""
        directory = self._root / narrator_id
        profile, _ = self._load(directory)
        return profile

    def list(self) -> list[NarratorProfile]:
        """Return valid profiles in deterministic ID order."""
        return self.discover()

    def validate(self, narrator_id: str | None = None) -> dict[str, Any]:
        """Validate one narrator ID or every narrator directory."""
        if narrator_id is not None:
            targets = [self._root / narrator_id]
        elif self._root.is_dir():
            targets = [path for path in self._root.iterdir() if path.is_dir()]
        else:
            targets = []

        errors: list[dict[str, str]] = []
        valid_ids: list[str] = []
        for target in targets:
            profile, profile_errors = self._load(target)
            if profile is None:
                errors.extend(profile_errors)
            else:
                valid_ids.append(profile.id)
        return {"ok": not errors, "errors": errors, "valid_ids": sorted(valid_ids)}

    def _load(self, directory: Path) -> tuple[NarratorProfile | None, list[dict[str, str]]]:
        errors: list[dict[str, str]] = []
        profile_path = directory / "profile.json"
        reference_path = directory / "reference.wav"
        if not directory.is_dir():
            return None, [self._error("narrator_not_found", f"Narrator directory does not exist: {directory}")]
        if not profile_path.is_file():
            errors.append(self._error("profile_not_found", f"Profile does not exist: {profile_path}"))
        if not reference_path.is_file():
            errors.append(self._error("reference_not_found", f"Reference audio does not exist: {reference_path}"))
        if errors:
            return None, errors
        try:
            with profile_path.open("r", encoding="utf-8") as file:
                data = json.load(file)
            profile = NarratorProfile.model_validate(data)
        except json.JSONDecodeError as exc:
            return None, [self._error("invalid_profile_json", str(exc))]
        except ValidationError as exc:
            return None, [self._error("invalid_profile", str(exc))]
        if profile.id != directory.name:
            return None, [
                self._error("profile_id_mismatch", f"Profile ID {profile.id!r} does not match directory {directory.name!r}")
            ]
        return profile.model_copy(update={"reference_path": reference_path}), []

    @staticmethod
    def _error(code: str, message: str) -> dict[str, str]:
        return {"code": code, "message": message}


__all__ = ["NarratorRegistry"]