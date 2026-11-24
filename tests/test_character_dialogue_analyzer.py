import unittest
import json
import tempfile
import shutil
from pathlib import Path
from pydantic import ValidationError

from app.book import SceneProfile, CharacterProfile, DialogueSegment, CharacterDialogueAnalyzer
from app.book.intelligence import LLMError


class MockLLMAdapter:
    """Mock LLM adapter to simulate LLM API responses for character/dialogue detection."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []
        self.responses: list[str] = []
        self.exception: Exception | None = None

    def add_response(self, text: str) -> None:
        self.responses.append(text)

    def generate(self, prompt: str, system_instruction: str | None = None) -> str:
        self.calls.append((prompt, system_instruction))
        if self.exception:
            raise self.exception
        if not self.responses:
            raise RuntimeError("No mock response configured")
        return self.responses.pop(0)


class CharacterDialogueAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.tmp_dir)
        self.mock_adapter = MockLLMAdapter()
        self.analyzer = CharacterDialogueAnalyzer(
            llm_adapter=self.mock_adapter,
            cache_dir=self.cache_dir,
            cache_enabled=True,
        )

        self.scene = SceneProfile(
            scene_id="s1",
            chapter_id="c1",
            start_text="Alice entered.",
            end_text="Bob nodded.",
            summary="Alice meets Bob.",
            scene_type="dialogue",
        )
        self.scene_text = "Alice entered. 'Hello Bob,' she said. Bob nodded in response."

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir)

    def test_analyzer_success_flow(self) -> None:
        self.mock_adapter.add_response(
            json.dumps({
                "characters": [
                    {"name": "Alice", "description": "Protagonist."},
                    {"name": "Bob", "description": "Supporting character."}
                ],
                "dialogue_segments": [
                    {
                        "speaker": "Alice",
                        "spoken_text": "Hello Bob,",
                        "surrounding_narration": "she said."
                    },
                    {
                        "speaker": None, # Unknown speaker allowed
                        "spoken_text": "Greetings,",
                        "surrounding_narration": "a voice whispered."
                    }
                ]
            })
        )

        chars, dialogues = self.analyzer.analyze(self.scene, self.scene_text)

        # Validate Characters
        self.assertEqual(len(chars), 2)
        self.assertEqual(chars[0].name, "Alice")
        self.assertEqual(chars[0].description, "Protagonist.")
        self.assertEqual(chars[1].name, "Bob")
        self.assertEqual(chars[1].description, "Supporting character.")

        # Validate Dialogue
        self.assertEqual(len(dialogues), 2)
        self.assertEqual(dialogues[0].speaker, "Alice")
        self.assertEqual(dialogues[0].spoken_text, "Hello Bob,")
        self.assertEqual(dialogues[0].surrounding_narration, "she said.")
        self.assertIsNone(dialogues[1].speaker)
        self.assertEqual(dialogues[1].spoken_text, "Greetings,")
        self.assertEqual(dialogues[1].surrounding_narration, "a voice whispered.")

        # Assert that cache file is created
        self.assertTrue(self.analyzer.cache_file.is_file())

    def test_analyzer_caching_behavior(self) -> None:
        # First run generates cache
        self.mock_adapter.add_response(
            json.dumps({
                "characters": [{"name": "Alice", "description": "Protagonist."}],
                "dialogue_segments": [
                    {
                        "speaker": "Alice",
                        "spoken_text": "Hi,",
                        "surrounding_narration": "she said."
                    }
                ]
            })
        )

        first_chars, first_dialogues = self.analyzer.analyze(self.scene, self.scene_text)
        self.assertEqual(len(first_chars), 1)

        # Second run: cache hit
        self.mock_adapter.exception = RuntimeError("LLM should not be called on cache hit")
        cached_chars, cached_dialogues = self.analyzer.analyze(self.scene, self.scene_text)
        self.assertEqual(len(cached_chars), 1)
        self.assertEqual(cached_chars[0].name, "Alice")
        self.assertEqual(cached_dialogues[0].spoken_text, "Hi,")

        # Third run: cache miss due to modified scene text
        self.mock_adapter.exception = None
        self.mock_adapter.add_response(
            json.dumps({
                "characters": [{"name": "Bob", "description": "Supporting character."}],
                "dialogue_segments": [
                    {
                        "speaker": "Bob",
                        "spoken_text": "No,",
                        "surrounding_narration": "he said."
                    }
                ]
            })
        )

        new_scene_text = "Bob entered. 'No,' he said."
        new_chars, new_dialogues = self.analyzer.analyze(self.scene, new_scene_text)
        self.assertEqual(len(new_chars), 1)
        self.assertEqual(new_chars[0].name, "Bob")
        self.assertEqual(new_dialogues[0].spoken_text, "No,")

    def test_analyzer_graceful_llm_failure(self) -> None:
        self.mock_adapter.exception = LLMError("API Connection Timeout")

        chars, dialogues = self.analyzer.analyze(self.scene, self.scene_text)

        # Fallback profile should be returned
        self.assertEqual(len(chars), 0)
        self.assertEqual(len(dialogues), 1)
        self.assertIsNone(dialogues[0].speaker)
        self.assertEqual(dialogues[0].spoken_text, "Alice entered. 'Hello Bob,' she said. Bob nodded in response.")
        self.assertEqual(dialogues[0].surrounding_narration, "Analysis unavailable (LLM or validation failure).")

    def test_analyzer_graceful_validation_failure(self) -> None:
        # Invalid: missing description in characters list
        self.mock_adapter.add_response(
            json.dumps({
                "characters": [{"name": "Alice"}],
                "dialogue_segments": []
            })
        )

        chars, dialogues = self.analyzer.analyze(self.scene, self.scene_text)

        # Fallback profile should be returned
        self.assertEqual(len(chars), 0)
        self.assertEqual(len(dialogues), 1)
        self.assertEqual(dialogues[0].surrounding_narration, "Analysis unavailable (LLM or validation failure).")

    def test_markdown_code_block_stripping(self) -> None:
        self.mock_adapter.add_response(
            '```json\n{\n  "characters": [\n    {"name": "Alice", "description": "Protagonist."}\n  ],\n  "dialogue_segments": [\n    {"speaker": "Alice", "spoken_text": "Hi", "surrounding_narration": null}\n  ]\n}\n```'
        )

        chars, dialogues = self.analyzer.analyze(self.scene, self.scene_text)
        self.assertEqual(len(chars), 1)
        self.assertEqual(chars[0].name, "Alice")
        self.assertEqual(dialogues[0].spoken_text, "Hi")


if __name__ == "__main__":
    unittest.main()
