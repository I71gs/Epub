# AI Audiobook Maker

AI Audiobook Maker is a Python application for converting EPUB and PDF books into narrated audiobook files. It combines book parsing, book intelligence, narration planning, narrator profiles, job tracking, and the `ebook2audiobook` (E2A) headless CLI.

## Current Features

- PDF and EPUB parsing
- Book metadata and chapter extraction
- Scene, character, dialogue, and narration analysis
- Narration plans compiled to E2A-compatible SML
- Narrator profile registry and validation
- Job state tracking
- Pipeline orchestration
- Command-line audiobook generation
- Automatic E2A entrypoint discovery
- Headless E2A subprocess execution
- Process cancellation and E2A session resume
- Structured subprocess output and diagnostics
- Local caching for book intelligence results
- Configurable application paths and logging

## Project Layout

```text
app/
  book/         PDF/EPUB parsing and book intelligence
  core/         Configuration and logging
  narration/    Narration plan compilation and smoke tests
  narrator/     Narrator models and registry
  pipeline/     Pipeline and job orchestration
  tts/          ebook2audiobook subprocess adapter
  ui/           Reserved for a future interface
  audio/        Reserved for audio processing
data/           Source and working data
narrators/      Narrator profiles and reference audio
output/         Generated audiobook files
tests/          Automated pytest suite
docs/           Architecture and integration documentation
```

## Requirements

- Python 3.11 or newer
- PyMuPDF
- Pydantic
- HTTPX
- An installed, reachable `ebook2audiobook` installation for real audiobook generation

Install Python dependencies:

```powershell
python -m pip install -r requirements.txt
```

## Configuration

Application paths can be overridden with environment variables:

| Variable | Purpose |
| --- | --- |
| `AUDIOBOOK_APP_NAME` | Application name |
| `AUDIOBOOK_LOG_LEVEL` | Logging level |
| `AUDIOBOOK_DATA_DIR` | Source and working data directory |
| `AUDIOBOOK_NARRATORS_DIR` | Narrator profile directory |
| `AUDIOBOOK_OUTPUT_DIR` | Generated audiobook directory |

E2A discovery uses these variables:

| Variable | Purpose |
| --- | --- |
| `E2A_ENTRYPOINT` | Direct path to an E2A launcher or entrypoint |
| `E2A_ROOT` | E2A installation directory |

Discovery priority is:

1. `E2A_ENTRYPOINT`
2. `E2A_ROOT`
3. A configured `E2AAdapter(entrypoint=...)`
4. `ebook2audiobook.cmd` or `ebook2audiobook` on `PATH`

### Windows PowerShell

```powershell
$env:E2A_ENTRYPOINT = "C:\tools\E2A\ebook2audiobook.cmd"
# or
$env:E2A_ROOT = "C:\tools\E2A"
```

### CMD

```cmd
set E2A_ENTRYPOINT=C:\tools\E2A\ebook2audiobook.cmd
```

### Linux or macOS

```bash
export E2A_ENTRYPOINT=/usr/local/bin/ebook2audiobook.sh
# or
export E2A_ROOT=/opt/ebook2audiobook
```

## Generate an Audiobook

Run the CLI from the project root:

```powershell
python -m app generate ".\book.epub" --language eng --output-format m4b
```

Available options:

```text
input_path                 EPUB or PDF source file
--language                 ISO language code; default: eng
--voice                    Voice reference audio file
--output-dir               Destination directory
--output-format            m4b or another format supported by E2A
--session                  E2A session ID for resume
```

The CLI validates EPUB/PDF input, voice-reference files, output directories, formats, and E2A entrypoints before generation starts.

## E2A Smoke Test

Verify E2A discovery and the minimal subprocess integration:

```powershell
python -m app.narration.smoke_test
```

The smoke test reports:

- Resolved E2A path
- Whether the entrypoint exists
- Whether it is executable
- Detected E2A root
- Discovery source
- A generated output path when conversion succeeds

## Run Tests

```powershell
python -m pytest
```

For a quick summary:

```powershell
python -m pytest -q
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [E2A narration capabilities](docs/E2A_NARRATION_CAPABILITIES.md)
- [LLM training and improvement roadmap](docs/LLM_TRAINING_ROADMAP.md)

## Current Limitations

- E2A is required for real audiobook generation.
- The UI and database packages are not implemented yet.
- The `app/audio` package is reserved for future audio post-processing.
- LLM providers require their own API keys or local runtime.
- PDF chapter boundaries may be less reliable than EPUB chapter boundaries.
- Final output naming and some progress details depend on the installed E2A version.
