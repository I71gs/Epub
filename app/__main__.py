"""Command-line entry point for the AI Audiobook Maker."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import sys

from app.core.config import load_settings
from app.core.logging_config import configure_logging, get_logger
from app.tts.e2a_adapter import E2AAdapter


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Audiobook Maker CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate = subparsers.add_parser(
        "generate", help="Generate an audiobook from a PDF or EPUB with E2A"
    )
    generate.add_argument("input_path", type=Path, help="Path to a PDF or EPUB file")
    generate.add_argument(
        "--language", default="eng", help="E2A language code (default: eng)"
    )
    generate.add_argument("--voice", dest="voice_path", type=Path, help="Voice reference audio path")
    generate.add_argument(
        "--output-dir", type=Path, default=None, help="Output directory (default: output)"
    )
    generate.add_argument(
        "--output-format", default="m4b", help="Audio format (default: m4b)"
    )
    generate.add_argument("--session", dest="session_id", help="E2A session ID to resume")
    return parser


def _generate(args: argparse.Namespace) -> int:
    settings = load_settings()
    output_dir = args.output_dir or settings.output_dir
    logger = get_logger(__name__)
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("Could not prepare output directory %s: %s", output_dir, exc)
        return 1

    request = {
        "input_path": args.input_path,
        "language": args.language,
        "voice_path": args.voice_path,
        "output_dir": output_dir,
        "output_format": args.output_format,
        "session_id": args.session_id,
    }
    result = E2AAdapter().generate(request)
    if not result["ok"]:
        for error in result["errors"]:
            logger.error("%s: %s", error["code"], error["message"])
        return 1

    print(result["output_path"])
    logger.info("Audiobook generated: %s", result["output_path"])
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    configure_logging(load_settings().log_level)
    if args.command == "generate":
        return _generate(args)
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    logging.getLogger(__name__).debug("Starting CLI")
    sys.exit(main())


__all__ = ["main"]