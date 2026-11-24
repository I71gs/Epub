import json
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError

from app.narrator import NarratorProfile, NarratorRegistry


class NarratorRegistryTests(unittest.TestCase):
    def _create_profile(self, root: Path, narrator_id: str = "alice") -> None:
        directory = root / narrator_id
        directory.mkdir()
        (directory / "profile.json").write_text(
            json.dumps({"id": narrator_id, "name": "Alice", "language": "eng"}),
            encoding="utf-8",
        )
        (directory / "reference.wav").write_bytes(b"fixture")

    def test_discover_get_and_list(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._create_profile(root)
            registry = NarratorRegistry(root)

            discovered = registry.discover()
            found = registry.get("alice")
            listed = registry.list()

        self.assertEqual([profile.id for profile in discovered], ["alice"])
        self.assertEqual(listed[0].name, "Alice")
        self.assertEqual(found.reference_path.name, "reference.wav")

    def test_validate_reports_missing_reference_and_excludes_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_dir = root / "broken"
            profile_dir.mkdir()
            (profile_dir / "profile.json").write_text(
                json.dumps({"id": "broken", "name": "Broken"}), encoding="utf-8"
            )
            registry = NarratorRegistry(root)

            result = registry.validate()

            self.assertFalse(result["ok"])
            self.assertEqual(result["errors"][0]["code"], "reference_not_found")
            self.assertEqual(registry.discover(), [])

    def test_profile_model_rejects_empty_name(self) -> None:
        with self.assertRaises(ValidationError):
            NarratorProfile(id="alice", name=" ")


if __name__ == "__main__":
    unittest.main()