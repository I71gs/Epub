"""Headless subprocess adapter for ebook2audiobook (E2A)."""

from __future__ import annotations

from pathlib import Path
import os
import queue
import shutil
import subprocess
import sys
import threading
from typing import Any

from app.core.logging_config import get_logger


def discover_e2a(configured_entrypoint: str | Path | None = None) -> dict[str, Any]:
    """Discover the E2A entrypoint path using standard priority rules and return diagnostics.

    Priority:
    1. E2A_ENTRYPOINT environment variable
    2. E2A_ROOT environment variable + ebook2audiobook.cmd
    3. Existing configured adapter path
    4. PATH lookup
    """
    env_entrypoint = os.getenv("E2A_ENTRYPOINT")
    env_root = os.getenv("E2A_ROOT")

    resolved_path: Path | None = None
    source: str = "none"
    e2a_root: Path | None = Path(env_root) if env_root and env_root.strip() else None

    # Priority 1: E2A_ENTRYPOINT environment variable
    if env_entrypoint and env_entrypoint.strip():
        source = "E2A_ENTRYPOINT"
        raw_path = Path(env_entrypoint.strip())
        if not raw_path.is_absolute() and len(raw_path.parts) == 1:
            which_res = shutil.which(str(raw_path))
            resolved_path = Path(which_res) if which_res else raw_path
        else:
            resolved_path = raw_path

    # Priority 2: E2A_ROOT environment variable + ebook2audiobook.cmd
    elif env_root and env_root.strip():
        source = "E2A_ROOT"
        root_dir = Path(env_root.strip())
        candidates = [
            root_dir / "ebook2audiobook.cmd",
            root_dir / "ebook2audiobook",
            root_dir / "ebook2audiobook.sh",
            root_dir / "ebook2audiobook.bat",
            root_dir / "app.py",
        ]
        chosen = None
        for cand in candidates:
            if cand.is_file():
                chosen = cand
                break
        resolved_path = chosen if chosen is not None else (root_dir / "ebook2audiobook.cmd")

    # Priority 3: Existing configured adapter path
    elif configured_entrypoint is not None and str(configured_entrypoint).strip() != "":
        source = "configured"
        raw_path = Path(configured_entrypoint)
        if not raw_path.is_absolute() and len(raw_path.parts) == 1:
            which_res = shutil.which(str(raw_path))
            resolved_path = Path(which_res) if which_res else raw_path
        else:
            resolved_path = raw_path

    # Priority 4: PATH lookup
    else:
        source = "PATH"
        default_cmd = "ebook2audiobook.cmd"
        which_res = shutil.which(default_cmd)
        if not which_res:
            which_res = shutil.which("ebook2audiobook") or shutil.which("ebook2audiobook.sh")
        if which_res:
            resolved_path = Path(which_res)
        else:
            resolved_path = Path(default_cmd)

    exists = resolved_path.is_file() if resolved_path else False
    is_executable = False
    if exists and resolved_path:
        if sys.platform == "win32":
            is_executable = os.access(resolved_path, os.X_OK) or resolved_path.suffix.lower() in {
                ".cmd",
                ".bat",
                ".exe",
                ".py",
                ".ps1",
                ".com",
            }
        else:
            is_executable = os.access(resolved_path, os.X_OK)

    if e2a_root is None:
        if exists and resolved_path:
            e2a_root = resolved_path.parent
        elif resolved_path and resolved_path.is_absolute():
            e2a_root = resolved_path.parent

    diagnostics = (
        f"Resolved E2A path: {resolved_path}\n"
        f"Exists: {exists}\n"
        f"Is Executable: {is_executable}\n"
        f"Detected E2A Root: {e2a_root}\n"
        f"Discovery Source: {source}"
    )

    return {
        "entrypoint": resolved_path,
        "resolved_path": str(resolved_path) if resolved_path else "",
        "exists": exists,
        "is_executable": is_executable,
        "e2a_root": str(e2a_root) if e2a_root else None,
        "source": source,
        "diagnostics": diagnostics,
    }


class E2AAdapter:
    """Run the pinned E2A CLI without importing E2A internals."""

    _SUPPORTED_INPUTS = {".pdf", ".epub", ".txt"}
    _SUPPORTED_OUTPUTS = {
        "aac",
        "flac",
        "mp3",
        "m4b",
        "m4a",
        "ogg",
        "mp4",
        "mov",
        "wav",
        "webm",
    }

    def __init__(self, entrypoint: str | Path | None = None) -> None:
        self._discovery = discover_e2a(entrypoint)
        self._entrypoint = self._discovery["entrypoint"]
        self._process: subprocess.Popen[str] | None = None
        self._request: dict[str, Any] | None = None
        self._session_id: str | None = None
        self._events: queue.Queue[tuple[str, str]] = queue.Queue()
        self._reader_threads: list[threading.Thread] = []
        self._state: dict[str, Any] = {
            "status": "idle",
            "phase": None,
            "progress": None,
            "stdout": "",
            "stderr": "",
            "error": None,
            "output_path": None,
            "returncode": None,
        }
        self._logger = get_logger(__name__)

    def validate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Validate an E2A request without starting a process."""
        errors: list[dict[str, str]] = []
        input_path = self._path_value(request, "input_path")
        output_dir = self._path_value(request, "output_dir")
        voice_path = self._path_value(request, "voice_path", required=False)
        output_format = str(request.get("output_format", "m4b")).lower().lstrip(".")

        if input_path is None:
            errors.append(self._error("missing_input", "input_path is required"))
        elif input_path.suffix.lower() not in self._SUPPORTED_INPUTS:
            errors.append(self._error("unsupported_input", "input_path must be PDF or EPUB"))
        elif not input_path.is_file():
            errors.append(self._error("input_not_found", f"Input file does not exist: {input_path}"))

        if output_dir is None:
            errors.append(self._error("missing_output_dir", "output_dir is required"))
        elif not output_dir.is_dir():
            errors.append(self._error("output_dir_not_found", f"Output directory does not exist: {output_dir}"))

        if output_format not in self._SUPPORTED_OUTPUTS:
            errors.append(self._error("unsupported_output", f"Unsupported output format: {output_format}"))

        if voice_path is not None and not voice_path.is_file():
            errors.append(self._error("voice_not_found", f"Voice file does not exist: {voice_path}"))

        if not self._entrypoint:
            errors.append(self._error("missing_entrypoint", "E2A entrypoint is not configured"))

        return {"ok": not errors, "errors": errors, "request": request}

    def generate(self, request: dict[str, Any]) -> dict[str, Any]:
        """Run E2A headlessly and return a structured result."""
        validation = self.validate(request)
        if not validation["ok"]:
            self._state.update(status="failed", error=validation["errors"])
            return self._result()

        self._request = dict(request)
        self._session_id = str(request.get("session_id") or "") or None
        output_dir = Path(request["output_dir"])
        before = {path.resolve() for path in output_dir.rglob("*") if path.is_file()}
        command = self._build_command(request)
        self._logger.info("Starting E2A headless conversion: %s", command)
        self._state.update(
            status="running",
            phase="starting",
            progress=None,
            stdout="",
            stderr="",
            error=None,
            output_path=None,
            returncode=None,
        )

        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                stdin=subprocess.DEVNULL,
            )
            self._reader_threads = []
            self._start_reader(self._process.stdout, "stdout")
            self._start_reader(self._process.stderr, "stderr")
            while self._process.poll() is None:
                self._drain_events()
            for thread in self._reader_threads:
                thread.join()
            self._drain_events()
            returncode = self._process.returncode
            self._state["returncode"] = returncode
            output_path = self._find_output(output_dir, before, request)
            self._state["output_path"] = str(output_path) if output_path else None
            if returncode == 0 and output_path:
                self._state.update(status="completed", phase="complete", progress=1.0)
            else:
                self._state.update(
                    status="failed",
                    phase="failed",
                    error=[self._error("conversion_failed", self._failure_message(returncode, output_path))],
                )
            return self._result()
        except OSError as exc:
            self._logger.exception("Could not start E2A")
            self._state.update(
                status="failed",
                phase="failed",
                error=[self._error("launch_failed", str(exc))],
            )
            return self._result()
        finally:
            self._process = None

    def progress(self) -> dict[str, Any]:
        """Return the latest parsed and captured subprocess progress."""
        self._drain_events()
        return self._result()

    def cancel(self) -> dict[str, Any]:
        """Terminate an active E2A process and return its final state."""
        if self._process is None or self._process.poll() is not None:
            return self._result()
        self._logger.info("Cancelling E2A session %s", self._session_id)
        self._process.terminate()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait()
        self._state.update(
            status="cancelled",
            phase="cancelled",
            error=[self._error("cancelled", "E2A conversion was cancelled")],
        )
        return self._result()

    def resume(self, session_id: str) -> dict[str, Any]:
        """Resume the last request using E2A's persisted session ID."""
        if not session_id:
            return {
                "ok": False,
                "status": "failed",
                "errors": [self._error("missing_session", "session_id is required")],
            }
        if self._request is None:
            return {
                "ok": False,
                "status": "failed",
                "errors": [self._error("no_request", "No previous request is available to resume")],
            }
        request = dict(self._request)
        request["session_id"] = session_id
        return self.generate(request)

    def _build_command(self, request: dict[str, Any]) -> list[str]:
        entrypoint = str(self._entrypoint)
        command = [entrypoint]
        if self._entrypoint.suffix.lower() == ".py":
            command = [sys.executable, entrypoint]
        command.extend(["--headless", "--ebook", str(Path(request["input_path"]).resolve())])
        command.extend(["--language", str(request.get("language", "eng"))])
        voice_path = request.get("voice_path")
        if voice_path:
            command.extend(["--voice", str(Path(voice_path).resolve())])
        command.extend(["--output_dir", str(Path(request["output_dir"]).resolve())])
        command.extend(["--output_format", str(request.get("output_format", "m4b")).lower().lstrip(".")])
        if request.get("session_id"):
            command.extend(["--session", str(request["session_id"])])
        return command

    def _start_reader(self, stream: Any, name: str) -> None:
        thread = threading.Thread(target=self._read_stream, args=(stream, name), daemon=True)
        thread.start()
        self._reader_threads.append(thread)

    def _read_stream(self, stream: Any, name: str) -> None:
        for line in iter(stream.readline, ""):
            self._events.put((name, line.rstrip()))
        stream.close()

    def _drain_events(self) -> None:
        while True:
            try:
                name, line = self._events.get_nowait()
            except queue.Empty:
                return
            self._state[name] += ("\n" if self._state[name] else "") + line
            if line:
                self._state["phase"] = line
                self._state["progress"] = self._parse_progress(line) or self._state["progress"]

    @staticmethod
    def _parse_progress(line: str) -> float | None:
        import re

        match = re.search(r"(\d+(?:\.\d+)?)%", line)
        return float(match.group(1)) / 100 if match else None

    @staticmethod
    def _path_value(request: dict[str, Any], key: str, required: bool = True) -> Path | None:
        value = request.get(key)
        if value is None or value == "":
            return None
        return Path(value)

    @staticmethod
    def _error(code: str, message: str) -> dict[str, str]:
        return {"code": code, "message": message}

    def _find_output(self, output_dir: Path, before: set[Path], request: dict[str, Any]) -> Path | None:
        output_format = str(request.get("output_format", "m4b")).lower().lstrip(".")
        candidates = [
            path
            for path in output_dir.rglob(f"*.{output_format}")
            if path.is_file() and path.stat().st_size > 0 and path.resolve() not in before
        ]
        return max(candidates, key=lambda path: path.stat().st_mtime, default=None)

    def _failure_message(self, returncode: int | None, output_path: Path | None) -> str:
        if returncode != 0:
            return f"E2A exited with return code {returncode}"
        return "E2A completed without producing a non-empty output file"

    @property
    def discovery_info(self) -> dict[str, Any]:
        """Return details and diagnostics from the E2A discovery process."""
        return dict(self._discovery)

    def _result(self) -> dict[str, Any]:
        return {
            "ok": self._state["status"] == "completed",
            "status": self._state["status"],
            "phase": self._state["phase"],
            "progress": self._state["progress"],
            "output_path": self._state["output_path"],
            "returncode": self._state["returncode"],
            "stdout": self._state["stdout"],
            "stderr": self._state["stderr"],
            "errors": self._state["error"] or [],
            "discovery": self._discovery,
        }


__all__ = ["E2AAdapter", "discover_e2a"]