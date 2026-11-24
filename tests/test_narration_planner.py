import unittest
import json
import tempfile
import shutil
from pathlib import Path
from pydantic import ValidationError

from app.book import SceneProfile, CharacterProfile, DialogueSegment, NarrationSegment, NarrationPlan, NarrationPlanner
from app.book.intelligence import LLMError


class MockLLMAdapter:
    """Mock LLM adapter to simulate LLM API responses for narration planning."""

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


class NarrationPlannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.mkdtemp()
        self.cache_dir = Path(self.tmp_dir)
        self.mock_adapter = MockLLMAdapter()
        self.planner = NarrationPlanner(
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
        self.characters = [
            CharacterProfile(name="Alice", description="Protagonist."),
            CharacterProfile(name="Bob", description="Supporting character.")
        ]
        self.dialogue_segments = [
            DialogueSegment(speaker="Alice", spoken_text="Hello Bob,", surrounding_narration="she said.")
        ]

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp_dir)

    def test_planner_success_flow(self) -> None:
        self.mock_adapter.add_response(
            json.dumps({
                "segments": [
                    {
                        "text": "Alice entered.",
                        "voice_role": "narrator",
                        "emotion": "neutral",
                        "intensity": 0.5,
                        "speaking_rate": 1.0,
                        "pause_before": 0.0,
                        "pause_after": 0.5,
                        "emphasis": "none"
                    },
                    {
                        "text": "'Hello Bob,'",
                        "voice_role": "Alice",
                        "emotion": "happy",
                        "intensity": 0.8,
                        "speaking_rate": 1.1,
                        "pause_before": 0.2,
                        "pause_after": 0.2,
                        "emphasis": "moderate"
                    }
                ]
            })
        )

        plan = self.planner.plan(self.scene, self.scene_text, self.characters, self.dialogue_segments)

        self.assertEqual(plan.scene_id, "s1")
        self.assertEqual(len(plan.segments), 2)
        
        self.assertEqual(plan.segments[0].text, "Alice entered.")
        self.assertEqual(plan.segments[0].voice_role, "narrator")
        self.assertEqual(plan.segments[0].emotion, "neutral")
        self.assertEqual(plan.segments[0].intensity, 0.5)
        self.assertEqual(plan.segments[0].speaking_rate, 1.0)
        self.assertEqual(plan.segments[0].pause_before, 0.0)
        self.assertEqual(plan.segments[0].pause_after, 0.5)
        self.assertEqual(plan.segments[0].emphasis, "none")

        self.assertEqual(plan.segments[1].text, "'Hello Bob,'")
        self.assertEqual(plan.segments[1].voice_role, "Alice")
        self.assertEqual(plan.segments[1].emotion, "happy")
        self.assertEqual(plan.segments[1].intensity, 0.8)
        self.assertEqual(plan.segments[1].speaking_rate, 1.1)
        self.assertEqual(plan.segments[1].pause_before, 0.2)
        self.assertEqual(plan.segments[1].pause_after, 0.2)
        self.assertEqual(plan.segments[1].emphasis, "moderate")

        # Assert cache file is created
        self.assertTrue(self.planner.cache_file.is_file())

    def test_planner_caching_behavior(self) -> None:
        # First run generates cache
        self.mock_adapter.add_response(
            json.dumps({
                "segments": [
                    {
                        "text": "Alice entered.",
                        "voice_role": "narrator",
                        "emotion": "neutral",
                        "intensity": 0.5,
                        "speaking_rate": 1.0,
                        "pause_before": 0.0,
                        "pause_after": 0.0,
                        "emphasis": "none"
                    }
                ]
            })
        )

        first_plan = self.planner.plan(self.scene, self.scene_text, self.characters, self.dialogue_segments)
        self.assertEqual(len(first_plan.segments), 1)

        # Second run: cache hit
        self.mock_adapter.exception = RuntimeError("LLM should not be called on cache hit")
        cached_plan = self.planner.plan(self.scene, self.scene_text, self.characters, self.dialogue_segments)
        self.assertEqual(len(cached_plan.segments), 1)
        self.assertEqual(cached_plan.segments[0].text, "Alice entered.")

        # Third run: cache miss due to modified scene text
        self.mock_adapter.exception = None
        self.mock_adapter.add_response(
            json.dumps({
                "segments": [
                    {
                        "text": "Bob entered.",
                        "voice_role": "narrator",
                        "emotion": "neutral",
                        "intensity": 0.5,
                        "speaking_rate": 1.0,
                        "pause_before": 0.0,
                        "pause_after": 0.0,
                        "emphasis": "none"
                    }
                ]
            })
        )

        new_scene_text = "Bob entered."
        new_plan = self.planner.plan(self.scene, new_scene_text, self.characters, self.dialogue_segments)
        self.assertEqual(len(new_plan.segments), 1)
        self.assertEqual(new_plan.segments[0].text, "Bob entered.")

    def test_planner_graceful_llm_failure(self) -> None:
        self.mock_adapter.exception = LLMError("API Connection Timeout")

        plan = self.planner.plan(self.scene, self.scene_text, self.characters, self.dialogue_segments)

        # Fallback profile should be returned
        self.assertEqual(plan.scene_id, "s1")
        self.assertEqual(len(plan.segments), 1)
        self.assertEqual(plan.segments[0].text, "Alice entered. 'Hello Bob,' she said. Bob nodded in response.")
        self.assertEqual(plan.segments[0].voice_role, "narrator")
        self.assertEqual(plan.segments[0].emotion, "neutral")

    def test_planner_graceful_validation_failure(self) -> None:
        # Invalid intensity: 1.5 is out of bounds (0.0-1.0)
        self.mock_adapter.add_response(
            json.dumps({
                "segments": [
                    {
                        "text": "Alice entered.",
                        "voice_role": "narrator",
                        "emotion": "neutral",
                        "intensity": 1.5,
                        "speaking_rate": 1.0,
                        "pause_before": 0.0,
                        "pause_after": 0.0,
                        "emphasis": "none"
                    }
                ]
            })
        )

        plan = self.planner.plan(self.scene, self.scene_text, self.characters, self.dialogue_segments)

        # Fallback profile should be returned
        self.assertEqual(len(plan.segments), 1)
        self.assertEqual(plan.segments[0].voice_role, "narrator")
        self.assertEqual(plan.segments[0].intensity, 0.5)

    def test_markdown_code_block_stripping(self) -> None:
        self.mock_adapter.add_response(
            '```json\n{\n  "segments": [\n    {\n      "text": "Alice",\n      "voice_role": "narrator",\n      "emotion": "neutral",\n      "intensity": 0.5,\n      "speaking_rate": 1.0,\n      "pause_before": 0.0,\n      "pause_after": 0.0,\n      "emphasis": "none"\n    }\n  ]\n}\n```'
        )

        plan = self.planner.plan(self.scene, self.scene_text, self.characters, self.dialogue_segments)
        self.assertEqual(len(plan.segments), 1)
        self.assertEqual(plan.segments[0].text, "Alice")


if __name__ == "__main__":
    unittest.main()
