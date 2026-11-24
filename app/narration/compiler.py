"""Narration Plan SML compiler for ebook2audiobook (E2A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.book.models import NarrationPlan, NarrationSegment

logger = logging.getLogger(__name__)


class CompilationResult(BaseModel):
    """Result of compiling a NarrationPlan into SML text."""

    sml_text: str
    metadata: dict[str, Any]
    warnings: list[str]


class NarrationCompiler:
    """Compiles a NarrationPlan into E2A-compatible SML text, gathering metadata and warnings."""

    def __init__(self, voice_map: dict[str, str | Path] | None = None) -> None:
        # Map voice_role to voice file path using forward slashes
        self.voice_map = {k: Path(v).as_posix() for k, v in (voice_map or {}).items()}

    def compile(self, plan: NarrationPlan) -> CompilationResult:
        """Compile a NarrationPlan into SML/text.

        Validates the plan, escapes sensitive characters, wraps voice roles,
        inserts pauses, and collects metadata and warnings for unsupported features.
        """
        if not plan.segments:
            raise ValueError("NarrationPlan contains no segments")

        sml_segments = []
        warnings = []
        speaking_rates = []
        emotions = []
        intensities = []
        emphases = []

        for idx, seg in enumerate(plan.segments):
            # 1. Collect metadata and warnings for unsupported/partially supported parameters
            speaking_rates.append(seg.speaking_rate)
            if seg.speaking_rate != 1.0:
                warnings.append(
                    f"Segment {idx} has speaking_rate={seg.speaking_rate} which is only partially supported (global CLI only)."
                )

            if seg.emotion != "neutral":
                warnings.append(
                    f"Segment {idx} has unsupported control: emotion='{seg.emotion}'."
                )
                emotions.append(seg.emotion)

            if seg.intensity != 0.5:
                warnings.append(
                    f"Segment {idx} has unsupported control: intensity={seg.intensity}."
                )
                intensities.append(seg.intensity)

            if seg.emphasis != "none":
                warnings.append(
                    f"Segment {idx} has unsupported control: emphasis='{seg.emphasis}'."
                )
                emphases.append(seg.emphasis)

            # 2. Process segment text and escape SML-sensitive characters ([ -> \[ and ] -> \])
            escaped_text = seg.text.replace("[", "\\[").replace("]", "\\]")

            # 3. Apply SML formatting for supported capabilities
            seg_sml = escaped_text

            # Wrap in voice tag if role is mapped to a voice path
            voice_path = self.voice_map.get(seg.voice_role)
            if voice_path:
                seg_sml = f"[voice:{voice_path}]{seg_sml}[/voice]"

            # Prepend pause_before if > 0.0
            if seg.pause_before > 0.0:
                seg_sml = f"[pause:{seg.pause_before:.3f}]{seg_sml}"

            # Append pause_after if > 0.0
            if seg.pause_after > 0.0:
                seg_sml = f"{seg_sml}[pause:{seg.pause_after:.3f}]"

            sml_segments.append(seg_sml)

        # Concat all segments deterministically
        sml_text = "".join(sml_segments)

        metadata = {
            "speaking_rates": speaking_rates,
            "emotions": emotions,
            "intensities": intensities,
            "emphases": emphases,
        }

        return CompilationResult(sml_text=sml_text, metadata=metadata, warnings=warnings)
