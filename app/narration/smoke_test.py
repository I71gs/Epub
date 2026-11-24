"""Smoke test tool to verify E2A audiobook integration."""

from __future__ import annotations

import os
import shutil
import tempfile
import wave
from pathlib import Path
from typing import Any

from app.book.models import NarrationPlan, NarrationSegment
from app.narration.compiler import NarrationCompiler
from app.tts.e2a_adapter import E2AAdapter, discover_e2a



def check_e2a_availability(entrypoint: str | Path | None = None) -> str | None:
    """Diagnose if the E2A entrypoint is executable and available."""
    discovery = discover_e2a(entrypoint)
    resolved = discovery["resolved_path"]
    exists = discovery["exists"]
    is_executable = discovery["is_executable"]
    e2a_root = discovery["e2a_root"]
    source = discovery["source"]

    diag_summary = (
        f"Diagnostics: resolved_path='{resolved}', exists={exists}, "
        f"is_executable={is_executable}, e2a_root={e2a_root}, source={source}."
    )

    if not exists:
        raw_path = Path(resolved) if resolved else Path()
        if source == "PATH" or len(raw_path.parts) <= 1:
            return (
                f"E2A entrypoint command '{resolved}' was not found in the system PATH. "
                f"{diag_summary} Please ensure E2A is installed or configure E2A_ENTRYPOINT or E2A_ROOT."
            )
        return (
            f"Specified E2A entrypoint file '{resolved}' does not exist on disk. "
            f"{diag_summary} Please ensure E2A is installed or configure E2A_ENTRYPOINT or E2A_ROOT."
        )

    if not is_executable:
        return (
            f"Specified E2A entrypoint file '{resolved}' is not executable. "
            f"{diag_summary}"
        )

    return None


def run_smoke_test() -> dict[str, Any]:
    """Execute the full SML compile -> E2A pipeline smoke test."""
    discovery = discover_e2a()
    blocker = check_e2a_availability()

    if blocker:
        return {
            "status": "BLOCKED",
            "blocker": blocker,
            "diagnostics": discovery["diagnostics"],
            "generated_file_path": None,
            "duration": None,
            "size": None,
        }

    # Setup temporary directory for test outputs
    tmp_dir = tempfile.mkdtemp()
    try:
        # 1. Test Sentence
        test_sentence = "This is a short public-domain sentence for integration testing."

        # 2. Minimal NarrationPlan
        segment = NarrationSegment(
            text=test_sentence,
            voice_role="narrator",
            emotion="neutral",
            intensity=0.5,
            speaking_rate=1.0,
            pause_before=0.0,
            pause_after=0.0,
            emphasis="none",
        )
        plan = NarrationPlan(scene_id="smoke-test-scene", segments=[segment])

        # 3. Compile plan
        compiler = NarrationCompiler()
        compilation_result = compiler.compile(plan)

        # 4. Save compiled SML/text to a temporary txt file
        input_txt_path = Path(tmp_dir) / "test_input.txt"
        input_txt_path.write_text(compilation_result.sml_text, encoding="utf-8")

        # 5. Initialize E2A adapter
        adapter = E2AAdapter(entrypoint=discovery["entrypoint"])

        # 6. E2A Request parameters (output to WAV for simple duration parsing)
        request = {
            "input_path": str(input_txt_path.resolve()),
            "language": "eng",
            "output_dir": str(Path(tmp_dir).resolve()),
            "output_format": "wav",
        }

        # Run conversion
        result = adapter.generate(request)

        if not result["ok"]:
            errors = "; ".join(e["message"] for e in result.get("errors", []))
            return {
                "status": "FAILED",
                "blocker": f"E2A subprocess failed: {errors}. Stdout: {result.get('stdout')}. Stderr: {result.get('stderr')}",
                "generated_file_path": None,
                "duration": None,
                "size": None,
            }

        output_path_str = result.get("output_path")
        if not output_path_str:
            return {
                "status": "FAILED",
                "blocker": "E2A completed successfully but produced no output path.",
                "generated_file_path": None,
                "duration": None,
                "size": None,
            }

        output_path = Path(output_path_str)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            return {
                "status": "FAILED",
                "blocker": f"Generated file '{output_path}' is empty or does not exist.",
                "generated_file_path": None,
                "duration": None,
                "size": None,
            }

        # Calculate file size and duration
        size_bytes = output_path.stat().st_size
        duration = 0.0
        try:
            with wave.open(str(output_path), "rb") as wav_file:
                frames = wav_file.getnframes()
                rate = wav_file.getframerate()
                duration = frames / float(rate)
        except Exception as e:
            # Fallback if ffmpeg output format or file is not standard WAV
            duration = -1.0

        # Move output file to permanent output folder for persistent testing if desired
        dest_dir = Path("output")
        dest_dir.mkdir(parents=True, exist_ok=True)
        final_output = dest_dir / output_path.name
        shutil.copy2(output_path, final_output)

        return {
            "status": "SUCCESS",
            "blocker": None,
            "generated_file_path": str(final_output.resolve()),
            "duration": duration,
            "size": size_bytes,
        }

    finally:
        shutil.rmtree(tmp_dir)


if __name__ == "__main__":
    import json

    res = run_smoke_test()
    print(json.dumps(res, indent=2))
