"""Command line: python -m letterbox LETTER_FILE"""

import argparse
import logging
import sys
from pathlib import Path
from typing import Callable, Sequence

import anthropic

from letterbox.graph import new_run_id, run
from letterbox.llm import ClaudeClient, LLMClient, LLMError

logger = logging.getLogger("letterbox")


def main(argv: Sequence[str] | None = None, client_factory: Callable[[], LLMClient] = ClaudeClient) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    letter = _read_letter(Path(args.letter_file))
    if letter is None:
        print("Could not read the letter file.", file=sys.stderr)
        return 1
    try:
        client = client_factory()
    except LLMError as error:
        print(error, file=sys.stderr)
        return 1
    return _run_and_print(letter, client)


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="letterbox", description="Explain an official letter in plain English and Farsi."
    )
    parser.add_argument("letter_file", help="path to a text file with the letter")
    return parser.parse_args(argv)


def _read_letter(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _run_and_print(letter: str, client: LLMClient) -> int:
    run_id = new_run_id()
    try:
        answer = run(letter, client, run_id=run_id)
    except anthropic.APIError as error:
        logger.error("run %s: model call failed: %s", run_id, error)
        print(f"Something went wrong. (Reference: {run_id})", file=sys.stderr)
        return 1
    print(answer.text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
