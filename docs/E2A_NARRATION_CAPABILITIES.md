# E2A Narration Capabilities Mapping

This document mappings `NarrationSegment` parameters to the capabilities supported by the pinned `ebook2audiobook` (E2A) and its associated SML (Speaker Markup Language) parsing engine.

## Overview of SML & E2A TTS Capabilities
E2A supports generating multi-speaker audiobooks by interpreting custom markup tags embedded directly within the text corpus. Fine-grained pacing and voice attributes are handled by specific SML tags or E2A CLI arguments.

---

## Parameter Mapping Matrix

| Parameter | E2A/SML Support Status | Translation Mechanism |
| :--- | :--- | :--- |
| **`voice_role`** | **SUPPORTED** | SML tag: `[voice:/path/to/voice/file]text[/voice]` |
| **`pause_before`** | **SUPPORTED** | SML tag: `[pause:N]` placed before the segment text (e.g. `[pause:0.5]`) |
| **`pause_after`** | **SUPPORTED** | SML tag: `[pause:N]` placed after the segment text (e.g. `[pause:0.8]`) |
| **`speaking_rate`** | **PARTIAL** | Subprocess argument: `--speed <float>` (processes the entire audio file at a global speed multiplier; no per-segment in-text SML control is available) |
| **`emotion`** | **UNSUPPORTED** | None (intonation is generated implicitly by XTTS or the underlying model based on text punctuation and reference audio) |
| **`intensity`** | **UNSUPPORTED** | None |
| **`emphasis`** | **UNSUPPORTED** | None |

---

## Detailed Control Documentation

### 1. `voice_role` (SUPPORTED)
*   **Classification:** `SUPPORTED`
*   **Translation Mechanism:**
    Multi-speaker generation is supported by wrapping the spoken text with the voice file path tag:
    ```text
    [voice:/path/to/voice/cloning/reference.wav]Character dialogue goes here.[/voice]
    ```
    E2A-SML parses this syntax and loads the specified voice-cloning sample file dynamically for that segment.
*   **Implementation Constraints:**
    The system must map named `voice_role` IDs (e.g. character profiles or narrator IDs) to valid physical audio references on disk before formatting the final SML text.

### 2. `pause_before` / `pause_after` (SUPPORTED)
*   **Classification:** `SUPPORTED`
*   **Translation Mechanism:**
    SML supports inserting silent gaps of custom lengths:
    *   **Fixed duration:** `[pause:N]` where `N` is a positive float representing seconds (e.g., `[pause:1.5]`).
    *   **Standard pauses:** `[break]` (random range 0.3 to 0.6 seconds) and `[pause]` (random range 1.0 to 1.6 seconds).
*   **Mapping implementation:**
    To introduce a pause before or after a segment, the SML generator inserts a `[pause:N]` tag immediately before or after the segment's text block.

### 3. `speaking_rate` (PARTIAL)
*   **Classification:** `PARTIAL`
*   **Translation Mechanism:**
    E2A accepts a `--speed <float>` CLI argument (e.g. `--speed 1.1` to speed up speech by 10%). This argument modifies the rate globally across the entire subprocess invocation.
*   **Limitations:**
    There is no supported SML tag to alter the speech rate dynamically for a single segment of text inside the corpus.

### 4. `emotion`, `intensity`, and `emphasis` (UNSUPPORTED)
*   **Classification:** `UNSUPPORTED`
*   **Translation Mechanism:**
    The XTTS model and the E2A parser do not support explicit parameterizations of emotion, emotional intensity, or emphasis tags. Voice style and emphasis are generated automatically by the TTS model based on:
    *   The structural style, punctuation, and wording of the input text itself.
    *   The baseline style and characteristics of the cloned reference audio file.
