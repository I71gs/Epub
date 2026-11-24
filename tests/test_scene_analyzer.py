import unittest
import json
import tempfile
import shutil
from pathlib import Path
from pydantic import ValidationError

from app.book import Chapter, SceneProfile, SceneAnalyzer
from app.book.intelligence import LLMError


class MockLLMAdapter:
    """Mock LLM adapter to simulate LLM API responses for scene detection."""

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


class SceneAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.tmp_dir)
        self.mock_adapter = MockLLMAdapter()
        self.analyzer = SceneAnalyzer(
            llm_adapter=self.mock_adapter,
            cache_dir=self.cache_dir,
            cache_enabled=True,
        )

        self.chapter = Chapter(
            id="c1",
            title="First Encounter",
            index=0,
            text="Alice walked into the room. 'Hello?' she whispered. Bob stood up and greeted her warmly. They shook hands.",
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir)

    def test_analyzer_success_flow(self) -> None:
        # Mock response returning structured scenes matching Pydantic validation
        self.mock_adapter.add_response(
            json.dumps({
                "scenes": [
                    {
                        "scene_id": "scene-1",
                        "start_text": "Alice walked into the room.",
                        "end_text": "'Hello?' she whispered.",
                        "summary": "Alice enters and calls out.",
                        "scene_type": "narration",
                    },
                    {
                        "scene_id": "scene-2",
                        "start_text": "Bob stood up and greeted her warmly.",
                        "end_text": "They shook hands.",
                        "summary": "Bob greets Alice.",
                        "scene_type": "action",
                    }
                ]
            })
        )

        scene_profiles = self.analyzer.analyze(self.chapter)

        self.assertEqual(len(scene_profiles), 2)
        self.assertEqual(scene_profiles[0].scene_id, "scene-1")
        self.assertEqual(scene_profiles[0].chapter_id, "c1")
        self.assertEqual(scene_profiles[0].start_text, "Alice walked into the room.")
        self.assertEqual(scene_profiles[0].end_text, "'Hello?' she whispered.")
        self.assertEqual(scene_profiles[0].summary, "Alice enters and calls out.")
        self.assertEqual(scene_profiles[0].scene_type, "narration")

        self.assertEqual(scene_profiles[1].scene_id, "scene-2")
        self.assertEqual(scene_profiles[1].chapter_id, "c1")
        self.assertEqual(scene_profiles[1].start_text, "Bob stood up and greeted her warmly.")
        self.assertEqual(scene_profiles[1].end_text, "They shook hands.")
        self.assertEqual(scene_profiles[1].summary, "Bob greets Alice.")
        self.assertEqual(scene_profiles[1].scene_type, "action")

        # Assert that cache file is created and non-empty
        self.assertTrue(self.analyzer.cache_file.is_file())

    def test_analyzer_caching_behavior(self) -> None:
        # First run generates cache
        self.mock_adapter.add_response(
            json.dumps({
                "scenes": [
                    {
                        "scene_id": "scene-1",
                        "start_text": "Alice walked into the room.",
                        "end_text": "They shook hands.",
                        "summary": "Meeting.",
                        "scene_type": "dialogue",
                    }
                ]
            })
        )

        first_runs = self.analyzer.analyze(self.chapter)
        self.assertEqual(len(first_runs), 1)

        # Second run should hit cache
        self.mock_adapter.exception = RuntimeError("LLM should not be called on cache hit")
        cached_runs = self.analyzer.analyze(self.chapter)

        self.assertEqual(len(cached_runs), 1)
        self.assertEqual(cached_runs[0].summary, "Meeting.")

        # Third run: modified chapter text should trigger cache miss and new LLM call
        self.mock_adapter.exception = None
        self.mock_adapter.add_response(
            json.dumps({
                "scenes": [
                    {
                        "scene_id": "scene-1",
                        "start_text": "Alice ran fast.",
                        "end_text": "She fell down.",
                        "summary": "Running.",
                        "scene_type": "action",
                    }
                ]
            })
        )

        modified_chapter = Chapter(
            id="c1",
            title="First Encounter",
            index=0,
            text="Alice ran fast. She fell down.",
        )
        new_runs = self.analyzer.analyze(modified_chapter)
        self.assertEqual(len(new_runs), 1)
        self.assertEqual(new_runs[0].summary, "Running.")

    def test_analyzer_graceful_llm_failure(self) -> None:
        self.mock_adapter.exception = LLMError("API Connection Timeout")

        scene_profiles = self.analyzer.analyze(self.chapter)

        # Fallback profile should be returned
        self.assertEqual(len(scene_profiles), 1)
        self.assertEqual(scene_profiles[0].scene_id, "c1-scene-fallback")
        self.assertEqual(scene_profiles[0].chapter_id, "c1")
        self.assertEqual(scene_profiles[0].summary, "Analysis unavailable (LLM or validation failure).")
        self.assertEqual(scene_profiles[0].scene_type, "other")

    def test_analyzer_graceful_validation_failure(self) -> None:
        # Return invalid scene_type
        self.mock_adapter.add_response(
            json.dumps({
                "scenes": [
                    {
                        "scene_id": "scene-1",
                        "start_text": "Alice walked into the room.",
                        "end_text": "They shook hands.",
                        "summary": "Meeting.",
                        "scene_type": "super-exciting-type", # invalid type
                    }
                ]
            })
        )

        scene_profiles = self.analyzer.analyze(self.chapter)

        # Fallback profile should be returned
        self.assertEqual(len(scene_profiles), 1)
        self.assertEqual(scene_profiles[0].scene_id, "c1-scene-fallback")
        self.assertEqual(scene_profiles[0].summary, "Analysis unavailable (LLM or validation failure).")
        self.assertEqual(scene_profiles[0].scene_type, "other")

    def test_markdown_code_block_stripping(self) -> None:
        self.mock_adapter.add_response(
            '```json\n{\n  "scenes": [\n    {\n      "scene_id": "scene-1",\n      "start_text": "Start",\n      "end_text": "End",\n      "summary": "Summary",\n      "scene_type": "narration"\n    }\n  ]\n}\n```'
        )

        scene_profiles = self.analyzer.analyze(self.chapter)
        self.assertEqual(len(scene_profiles), 1)
        self.assertEqual(scene_profiles[0].summary, "Summary")


if __name__ == "__main__":
    unittest.main()
