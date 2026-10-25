"""Eval: run every letter through the real pipeline and compare with its answer key.

Run with `python -m eval.run`. It calls the real model, so it needs
ANTHROPIC_API_KEY and costs money; it is not run in CI.
"""

import argparse
import logging
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import anthropic

from letterbox.graph import run_state
from letterbox.llm import MODEL, ClaudeClient, LLMClient, LLMError
from letterbox.logging_setup import configure_logging
from letterbox.schema import FactKind, LetterFacts
from letterbox.text import normalize_whitespace
from letterbox.verify import FactStatus, VerifiedFacts

ROOT = Path(__file__).resolve().parent.parent
LETTERS_DIR = ROOT / "data" / "letters"
RESULTS_PATH = Path(__file__).resolve().parent / "RESULTS.md"
SCORED_KINDS = (FactKind.DEADLINE, FactKind.AMOUNT, FactKind.DATE)

logger = logging.getLogger("letterbox.eval")

KindCounts = dict[FactKind, int]


@dataclass(frozen=True)
class Comparison:
    correct: KindCounts
    expected: KindCounts
    not_sure: int
    dropped: int
    extra: int = 0  # verified deadlines, amounts and dates that are not in the answer key


@dataclass(frozen=True)
class LetterResult:
    letter: str
    outcome: str
    comparison: Comparison
    model_calls: int


@dataclass(frozen=True)
class RunInfo:
    """What the header of RESULTS.md says about the run."""

    model: str
    run_at: str
    commit: str
    letters_run: int
    letters_available: int
    limit: int | None = None


class CountingClient:
    """Passes calls through to another client and counts them."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        return self.inner.complete(system, user)


def compare(key: LetterFacts, verified: VerifiedFacts | None) -> Comparison:
    """Count key values found as verified facts of the same kind, extras, and not-sure and dropped facts."""
    found = [] if verified is None else [c.fact for c in verified.facts if c.status is FactStatus.VERIFIED]
    correct, expected, extra = {}, {}, 0
    for kind in SCORED_KINDS:
        wanted = Counter(_comparable(fact.value) for fact in key.facts if fact.kind is kind)
        got = Counter(_comparable(fact.value) for fact in found if fact.kind is kind)
        expected[kind] = sum(wanted.values())
        correct[kind] = sum((wanted & got).values())
        extra += sum((got - wanted).values())
    if verified is None:
        return Comparison(correct, expected, not_sure=0, dropped=0)
    not_sure = sum(1 for checked in verified.facts if checked.status is FactStatus.NOT_SURE)
    return Comparison(correct, expected, not_sure=not_sure, dropped=len(verified.dropped), extra=extra)


def _comparable(value: str) -> str:
    return normalize_whitespace(value).strip(" .,;:")


def outcome(state: Mapping[str, Any]) -> str:
    """"ok", or which steps were not sure."""
    for key, step in (("facts", "extract"), ("verified", "verify"), ("explanation", "explain")):
        if key not in state:
            return f"not sure at {step}"
    unsure = [step for key, step in (("option_list", "options"), ("reply_draft", "reply")) if state.get(key) is None]
    return f"not sure at {', '.join(unsure)}" if unsure else "ok"


def evaluate_letter(letter_path: Path, client: LLMClient) -> LetterResult:
    key = LetterFacts.model_validate_json(letter_path.with_suffix(".expected.json").read_text(encoding="utf-8"))
    counting = CountingClient(client)
    try:
        state = run_state(letter_path.read_text(encoding="utf-8"), counting)
    except anthropic.APIError as error:
        logger.error("letter %s: step=model_call error=%s", letter_path.stem, type(error).__name__)
        return LetterResult(letter_path.stem, f"error: {type(error).__name__}", compare(key, None), counting.calls)
    comparison = compare(key, state.get("verified"))
    return LetterResult(letter_path.stem, outcome(state), comparison, counting.calls)


def letter_paths(letters_dir: Path) -> list[Path]:
    return sorted(letters_dir.glob("*.txt"))


def run_eval(letters_dir: Path, client: LLMClient, limit: int | None = None) -> list[LetterResult]:
    """Evaluate the letters in name order; with `limit`, only the first `limit` of them."""
    return [evaluate_letter(path, client) for path in letter_paths(letters_dir)[:limit]]


def git_commit() -> str:
    """The short commit hash, noting uncommitted changes, or "unknown" without git."""
    try:
        commit = _git("rev-parse", "--short", "HEAD")
        changes = _git("status", "--porcelain", "--", ".", f":!{RESULTS_PATH.relative_to(ROOT)}")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{commit} (with uncommitted changes)" if changes else commit


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def format_results(results: list[LetterResult], info: RunInfo) -> str:
    header = "| Letter | Outcome | Deadlines | Amounts | Dates | Extra | Not sure | Dropped | Model calls |"
    lines = [
        "# Eval results",
        "",
        f"- Model: `{info.model}`",
        f"- Run at: {info.run_at}",
        f"- Letters run: {_letters_run(info)}",
        f"- Git commit: {info.commit}",
        "",
        header,
        "|---|---|---|---|---|---|---|---|---|",
        *(_row(result.letter, result.outcome, result.comparison, result.model_calls) for result in results),
        _row("**Total**", _total_outcome(results), _total(results), sum(r.model_calls for r in results)),
        "",
        "Deadlines, amounts and dates: answer-key values found as verified facts of the same kind.",
        "Extra: verified deadlines, amounts and dates that are not in the answer key.",
        "Not sure and dropped: facts the verify step marked not sure or dropped.",
        "Model calls include retries.",
    ]
    return "\n".join(lines) + "\n"


def _letters_run(info: RunInfo) -> str:
    if info.limit is None:
        return str(info.letters_run)
    return f"{info.letters_run} of {info.letters_available} (limited with --limit {info.limit})"


def _row(letter: str, result_outcome: str, comparison: Comparison, calls: int) -> str:
    scores = " | ".join(f"{comparison.correct[kind]}/{comparison.expected[kind]}" for kind in SCORED_KINDS)
    counts = f"{comparison.extra} | {comparison.not_sure} | {comparison.dropped} | {calls}"
    return f"| {letter} | {result_outcome} | {scores} | {counts} |"


def _total(results: list[LetterResult]) -> Comparison:
    return Comparison(
        correct={kind: sum(r.comparison.correct[kind] for r in results) for kind in SCORED_KINDS},
        expected={kind: sum(r.comparison.expected[kind] for r in results) for kind in SCORED_KINDS},
        not_sure=sum(r.comparison.not_sure for r in results),
        dropped=sum(r.comparison.dropped for r in results),
        extra=sum(r.comparison.extra for r in results),
    )


def _total_outcome(results: list[LetterResult]) -> str:
    return f"{sum(1 for r in results if r.outcome == 'ok')}/{len(results)} ok"


def main(
    argv: Sequence[str] = (),
    output: Path = RESULTS_PATH,
    letters_dir: Path = LETTERS_DIR,
    client_factory: Callable[[], LLMClient] = ClaudeClient,
) -> int:
    args = _parse_args(argv)
    configure_logging()
    try:
        client = client_factory()
    except LLMError as error:
        print(error, file=sys.stderr)
        return 1
    results = run_eval(letters_dir, client, limit=args.limit)
    info = RunInfo(
        model=MODEL,
        run_at=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        commit=git_commit(),
        letters_run=len(results),
        letters_available=len(letter_paths(letters_dir)),
        limit=args.limit,
    )
    table = format_results(results, info)
    output.write_text(table, encoding="utf-8")
    print(table)
    return 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m eval.run", description="Run the eval with the real model.")
    parser.add_argument("--limit", type=_positive_int, help="run only the first N letters")
    return parser.parse_args(argv)


def _positive_int(text: str) -> int:
    try:
        number = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("must be a whole number") from None
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
