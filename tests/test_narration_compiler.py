import unittest
from pathlib import Path

from app.book.models import NarrationPlan, NarrationSegment
from app.narration.compiler import NarrationCompiler


class NarrationCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.voice_map = {
            "narrator": "voices/narrator.wav",
            "Alice": "voices/alice.wav",
            "Bob": Path("voices/bob.wav"),
        }
        self.compiler = NarrationCompiler(voice_map=self.voice_map)

    def test_compiler_normal_narration(self) -> None:
        segment = NarrationSegment(
            text="Hello world.",
            voice_role="narrator",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.0,
            pause_after=0.0,
            emphasis="none",
        )
        plan = NarrationPlan(scene_id="s1", segments=[segment])

        result = self.compiler.compile(plan)

        self.assertEqual(result.sml_text, "[voice:voices/narrator.wav]Hello world.[/voice]")
        self.assertEqual(len(result.warnings), 0)
        self.assertEqual(result.metadata["speaking_rates"], [1.0])

    def test_compiler_pauses(self) -> None:
        segment = NarrationSegment(
            text="Paused segment.",
            voice_role="narrator",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.5,
            pause_after=1.234,
            emphasis="none",
        )
        plan = NarrationPlan(scene_id="s1", segments=[segment])

        result = self.compiler.compile(plan)

        # Pause values formatted to 3 decimal places
        self.assertEqual(
            result.sml_text,
            "[pause:0.500][voice:voices/narrator.wav]Paused segment.[/voice][pause:1.234]",
        )

    def test_compiler_voice_switching(self) -> None:
        segment_narrator = NarrationSegment(
            text="She said,",
            voice_role="narrator",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.0,
            pause_after=0.0,
            emphasis="none",
        )
        segment_alice = NarrationSegment(
            text="'Hello!'",
            voice_role="Alice",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.0,
            pause_after=0.0,
            emphasis="none",
        )
        segment_unmapped = NarrationSegment(
            text="whispered Charlie.",
            voice_role="Charlie",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.0,
            pause_after=0.0,
            emphasis="none",
        )
        plan = NarrationPlan(
            scene_id="s1",
            segments=[segment_narrator, segment_alice, segment_unmapped],
        )

        result = self.compiler.compile(plan)

        expected = (
            "[voice:voices/narrator.wav]She said,[/voice]"
            "[voice:voices/alice.wav]'Hello!'[/voice]"
            "whispered Charlie."
        )
        self.assertEqual(result.sml_text, expected)

    def test_compiler_multiple_segments(self) -> None:
        segment1 = NarrationSegment(
            text="Segment one.",
            voice_role="narrator",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.1,
            pause_after=0.0,
            emphasis="none",
        )
        segment2 = NarrationSegment(
            text="Segment two.",
            voice_role="Bob",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.0,
            pause_after=0.2,
            emphasis="none",
        )
        plan = NarrationPlan(scene_id="s1", segments=[segment1, segment2])

        result = self.compiler.compile(plan)

        expected = (
            "[pause:0.100][voice:voices/narrator.wav]Segment one.[/voice]"
            "[voice:voices/bob.wav]Segment two.[/voice][pause:0.200]"
        )
        self.assertEqual(result.sml_text, expected)

    def test_compiler_unsupported_controls(self) -> None:
        segment = NarrationSegment(
            text="Emphasised speech.",
            voice_role="narrator",
            emotion="angry",
            intensity=0.9,
            speaking_rate=1.2,
            pause_before=0.0,
            pause_after=0.0,
            emphasis="strong",
        )
        plan = NarrationPlan(scene_id="s1", segments=[segment])

        result = self.compiler.compile(plan)

        # Check warnings are generated
        self.assertEqual(len(result.warnings), 4)
        self.assertIn("speaking_rate=1.2", result.warnings[0])
        self.assertIn("emotion='angry'", result.warnings[1])
        self.assertIn("intensity=0.9", result.warnings[2])
        self.assertIn("emphasis='strong'", result.warnings[3])

        # Metadata stores values
        self.assertEqual(result.metadata["speaking_rates"], [1.2])
        self.assertEqual(result.metadata["emotions"], ["angry"])
        self.assertEqual(result.metadata["intensities"], [0.9])
        self.assertEqual(result.metadata["emphases"], ["strong"])

        # SML text compiles with supported controls only
        self.assertEqual(result.sml_text, "[voice:voices/narrator.wav]Emphasised speech.[/voice]")

    def test_compiler_malformed_input(self) -> None:
        plan = NarrationPlan(scene_id="s1", segments=[])
        with self.assertRaises(ValueError):
            self.compiler.compile(plan)

    def test_compiler_special_characters(self) -> None:
        segment = NarrationSegment(
            text="Bracketed [test] text [here].",
            voice_role="narrator",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.0,
            pause_after=0.0,
            emphasis="none",
        )
        plan = NarrationPlan(scene_id="s1", segments=[segment])

        result = self.compiler.compile(plan)

        # Escapes [ and ]
        self.assertEqual(
            result.sml_text,
            "[voice:voices/narrator.wav]Bracketed \\[test\\] text \\[here\\].[/voice]",
        )


if __name__ == "__main__":
    unittest.main()
