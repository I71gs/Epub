# AI Audiobook Maker

A Python foundation for turning books into narrated audiobooks.

## Sprint 1 Task 1

This first slice contains the package layout, standard-library configuration, and logging only. TTS, LLM, UI, database, and E2A integrations are intentionally not implemented.

## Run checks

From the project root:

```powershell
python -m pytest
```

Configuration can be overridden with `AUDIOBOOK_APP_NAME`, `AUDIOBOOK_LOG_LEVEL`, `AUDIOBOOK_DATA_DIR`, `AUDIOBOOK_NARRATORS_DIR`, and `AUDIOBOOK_OUTPUT_DIR`.

## E2A Setup & Discovery

The system automatically discovers the `ebook2audiobook` (E2A) installation using the following priority:

1. **`E2A_ENTRYPOINT` environment variable**: Direct path to the E2A executable or script (e.g. `C:\tools\E2A\ebook2audiobook.cmd`).
2. **`E2A_ROOT` environment variable**: Directory containing the E2A installation root (resolves to `ebook2audiobook.cmd` or standard entrypoint script in that directory).
3. **Configured adapter path**: Path explicitly passed when initializing `E2AAdapter(entrypoint=...)`.
4. **PATH lookup**: System `PATH` search for `ebook2audiobook.cmd` (or `ebook2audiobook`).

### Setup Instructions

To configure E2A:

**Windows PowerShell:**
```powershell
# Option 1: Direct entrypoint path
$env:E2A_ENTRYPOINT = "C:\path\to\ebook2audiobook.cmd"

# Option 2: E2A installation root
$env:E2A_ROOT = "C:\path\to\ebook2audiobook"
```

**CMD:**
```cmd
set E2A_ENTRYPOINT=C:\path\to\ebook2audiobook.cmd
set E2A_ROOT=C:\path\to\ebook2audiobook
```

**Linux/macOS:**
```bash
export E2A_ENTRYPOINT=/usr/local/bin/ebook2audiobook.sh
export E2A_ROOT=/opt/ebook2audiobook
```

### Running the E2A Integration Smoke Test

To verify your E2A configuration:

```powershell
python -m app.narration.smoke_test
```

The smoke test will output diagnostic status detailing:
- Resolved E2A path
- Whether it exists
- Whether it is executable
- Detected E2A root
- Discovery source

