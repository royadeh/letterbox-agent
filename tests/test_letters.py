import json
from pathlib import Path
from typing import Any

import pytest

from letterbox.schema import LetterFacts
from letterbox.text import appears_in

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"
MIN_LETTERS = 8


def letter_paths() -> list[Path]:
    return sorted(LETTERS_DIR.glob("*.txt"))


def key_path(letter: Path) -> Path:
    return letter.with_suffix(".expected.json")


def load_key(letter: Path) -> dict[str, Any]:
    return json.loads(key_path(letter).read_text(encoding="utf-8"))


def test_there_are_enough_letters() -> None:
    assert len(letter_paths()) >= MIN_LETTERS


@pytest.mark.parametrize("letter", letter_paths(), ids=lambda p: p.stem)
def test_every_letter_has_an_answer_key(letter: Path) -> None:
    assert key_path(letter).is_file()


@pytest.mark.parametrize("letter", letter_paths(), ids=lambda p: p.stem)
def test_every_supporting_sentence_appears_in_its_letter(letter: Path) -> None:
    text = letter.read_text(encoding="utf-8")
    facts = load_key(letter)["facts"]
    assert facts
    for fact in facts:
        evidence = fact["evidence"]
        assert evidence.strip(), f"empty evidence for {fact}"
        assert appears_in(evidence, text), f"not in letter: {evidence!r}"


EXACT_VALUE_KINDS = {"sender", "reference", "amount", "deadline", "date"}
LABELLED_KINDS = {"amount", "deadline", "date"}


@pytest.mark.parametrize("letter", letter_paths(), ids=lambda p: p.stem)
def test_exact_values_appear_in_their_evidence(letter: Path) -> None:
    for fact in load_key(letter)["facts"]:
        if fact["kind"] in EXACT_VALUE_KINDS:
            assert appears_in(fact["value"], fact["evidence"]), fact


@pytest.mark.parametrize("letter", letter_paths(), ids=lambda p: p.stem)
def test_labels_are_optional_and_only_on_amounts_deadlines_and_dates(letter: Path) -> None:
    for fact in load_key(letter)["facts"]:
        if "label" in fact:
            assert fact["kind"] in LABELLED_KINDS, fact
            assert isinstance(fact["label"], str) and fact["label"].strip(), fact


@pytest.mark.parametrize("letter", letter_paths(), ids=lambda p: p.stem)
def test_conditions_are_copied_from_their_evidence(letter: Path) -> None:
    for fact in load_key(letter)["facts"]:
        if "condition" in fact:
            assert appears_in(fact["condition"], fact["evidence"]), fact


@pytest.mark.parametrize("letter", letter_paths(), ids=lambda p: p.stem)
def test_answer_key_loads_into_schema(letter: Path) -> None:
    LetterFacts.model_validate_json(key_path(letter).read_text(encoding="utf-8"))
