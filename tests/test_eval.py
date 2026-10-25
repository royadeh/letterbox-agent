import json
from pathlib import Path
from typing import Any

import pytest

from conftest import LETTERS_DIR, FakeLLM
from eval.run import (
    Comparison,
    CountingClient,
    LetterResult,
    compare,
    evaluate_letter,
    format_results,
    main,
    outcome,
    run_eval,
)
from letterbox.schema import Fact, FactKind, LetterFacts
from letterbox.verify import verify

STATEMENT = LETTERS_DIR / "006_two_amounts_statement.txt"


def key_for(letter: Path) -> LetterFacts:
    return LetterFacts.model_validate_json(letter.with_suffix(".expected.json").read_text(encoding="utf-8"))


def fact(**fields: Any) -> Fact:
    return Fact.model_validate(fields)


def with_facts(*facts: Fact) -> LetterFacts:
    return LetterFacts(facts=list(facts))


MINIMUM = fact(kind="amount", value="$75.00", evidence="Your minimum payment is $75.00.")
BALANCE = fact(kind="amount", value="$2,460.00", evidence="Your total balance is $2,460.00.")
DUE = fact(kind="deadline", value="December 5, 2026", evidence="The minimum payment is due on December 5, 2026.")


@pytest.mark.parametrize("letter", sorted(LETTERS_DIR.glob("*.txt")), ids=lambda p: p.stem)
def test_answer_key_compared_with_itself_is_fully_correct(letter: Path) -> None:
    key = key_for(letter)
    result = compare(key, verify(key, letter.read_text(encoding="utf-8")))
    assert result.correct == result.expected
    assert result.not_sure == result.dropped == 0


def test_expected_counts_come_from_the_answer_key() -> None:
    result = compare(key_for(STATEMENT), None)
    assert result.expected == {FactKind.DEADLINE: 1, FactKind.AMOUNT: 2, FactKind.DATE: 0}
    assert result.correct == {FactKind.DEADLINE: 0, FactKind.AMOUNT: 0, FactKind.DATE: 0}


def test_wrong_amount_is_not_correct_and_counts_as_not_sure() -> None:
    wrong = fact(kind="amount", value="$57.00", evidence="Your minimum payment is $75.00.")
    letter = STATEMENT.read_text(encoding="utf-8")
    result = compare(key_for(STATEMENT), verify(with_facts(BALANCE, wrong, DUE), letter))
    assert result.correct[FactKind.AMOUNT] == 1
    assert result.correct[FactKind.DEADLINE] == 1
    assert result.not_sure == 1


def test_dropped_facts_are_counted() -> None:
    made_up = fact(kind="purpose", value="A notice.", evidence="This sentence is not in the letter.")
    letter = STATEMENT.read_text(encoding="utf-8")
    assert compare(key_for(STATEMENT), verify(with_facts(MINIMUM, made_up), letter)).dropped == 1


def test_missing_deadline_is_not_correct() -> None:
    letter = STATEMENT.read_text(encoding="utf-8")
    result = compare(key_for(STATEMENT), verify(with_facts(MINIMUM, BALANCE), letter))
    assert result.correct[FactKind.DEADLINE] == 0
    assert result.correct[FactKind.AMOUNT] == 2


def test_the_same_fact_found_twice_counts_once() -> None:
    letter = STATEMENT.read_text(encoding="utf-8")
    result = compare(key_for(STATEMENT), verify(with_facts(MINIMUM, MINIMUM), letter))
    assert result.correct[FactKind.AMOUNT] == 1


def test_a_value_under_the_wrong_kind_is_not_correct() -> None:
    as_date = fact(kind="date", value="December 5, 2026", evidence="The minimum payment is due on December 5, 2026.")
    letter = STATEMENT.read_text(encoding="utf-8")
    result = compare(key_for(STATEMENT), verify(with_facts(as_date), letter))
    assert result.correct[FactKind.DEADLINE] == 0
    assert result.correct[FactKind.DATE] == 0


def test_values_match_ignoring_spacing_and_end_punctuation() -> None:
    spaced = fact(kind="deadline", value="December  5,\n2026.", evidence="The minimum payment is due on December 5, 2026.")
    letter = STATEMENT.read_text(encoding="utf-8")
    assert compare(key_for(STATEMENT), verify(with_facts(spaced), letter)).correct[FactKind.DEADLINE] == 1


@pytest.mark.parametrize(
    "state, expected",
    [
        ({}, "not sure at extract"),
        ({"facts": "x"}, "not sure at verify"),
        ({"facts": "x", "verified": "x"}, "not sure at explain"),
        ({"facts": "x", "verified": "x", "explanation": "x", "option_list": None, "reply_draft": "x"}, "not sure at options"),
        ({"facts": "x", "verified": "x", "explanation": "x", "option_list": None, "reply_draft": None}, "not sure at options, reply"),
        ({"facts": "x", "verified": "x", "explanation": "x", "option_list": "x", "reply_draft": "x"}, "ok"),
    ],
)
def test_outcome_names_the_step_that_was_not_sure(state: dict[str, Any], expected: str) -> None:
    assert outcome(state) == expected


def test_counting_client_counts_every_call() -> None:
    client = CountingClient(FakeLLM(["a", "b"]))
    client.complete("system", "one")
    client.complete("system", "two")
    assert client.calls == 2


def statement_responses() -> list[str]:
    key = STATEMENT.with_suffix(".expected.json").read_text(encoding="utf-8")
    explain = json.dumps(
        {"items": [{"fact": f"F{n}", "english": f"Point: {{F{n}}}.", "farsi": f"نکته: {{F{n}}}."} for n in range(1, 7)]},
        ensure_ascii=False,
    )
    reply = json.dumps(
        {"reply": "Dear {F1},\n\nRe: {F2}\n\nThank you.\n\n[Your name]", "farsi_explanation": "این پیش‌نویس {F2} را ذکر می‌کند."},
        ensure_ascii=False,
    )
    return [key, explain, reply]  # 006 has no actions, so the options step makes no call


def test_evaluate_letter_runs_the_real_pipeline_with_the_given_client() -> None:
    result = evaluate_letter(STATEMENT, FakeLLM(statement_responses()))
    assert result.letter == "006_two_amounts_statement"
    assert result.outcome == "ok"
    assert result.model_calls == 3
    assert result.comparison.correct == result.comparison.expected


def test_evaluate_letter_when_extract_is_not_sure() -> None:
    result = evaluate_letter(STATEMENT, FakeLLM(["not json", "not json"]))
    assert result.outcome == "not sure at extract"
    assert result.model_calls == 2
    assert result.comparison.correct[FactKind.AMOUNT] == 0


def test_run_eval_covers_every_letter_in_the_folder(tmp_path: Path) -> None:
    for suffix in (".txt", ".expected.json"):
        (tmp_path / f"006_two_amounts_statement{suffix}").write_text(
            STATEMENT.with_suffix(suffix).read_text(encoding="utf-8"), encoding="utf-8"
        )
    results = run_eval(tmp_path, FakeLLM(statement_responses()))
    assert [result.letter for result in results] == ["006_two_amounts_statement"]


def sample_results() -> list[LetterResult]:
    full = {FactKind.DEADLINE: 1, FactKind.AMOUNT: 2, FactKind.DATE: 0}
    half = {FactKind.DEADLINE: 0, FactKind.AMOUNT: 1, FactKind.DATE: 0}
    return [
        LetterResult("006_two_amounts_statement", "ok", Comparison(full, full, not_sure=0, dropped=0), model_calls=3),
        LetterResult("009_example", "not sure at options", Comparison(half, full, not_sure=1, dropped=2), model_calls=5),
    ]


def test_results_table_has_a_row_per_letter_and_a_total() -> None:
    table = format_results(sample_results(), model="claude-sonnet-5-5", day="2026-10-25")
    assert "| Letter | Outcome | Deadlines | Amounts | Dates | Not sure | Dropped | Model calls |" in table
    assert "| 006_two_amounts_statement | ok | 1/1 | 2/2 | 0/0 | 0 | 0 | 3 |" in table
    assert "| 009_example | not sure at options | 0/1 | 1/2 | 0/0 | 1 | 2 | 5 |" in table
    assert "| **Total** | 1/2 ok | 1/2 | 3/4 | 0/0 | 1 | 2 | 8 |" in table
    assert "claude-sonnet-5-5" in table and "2026-10-25" in table


def test_main_without_an_api_key_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output = tmp_path / "RESULTS.md"
    assert main(output=output) == 1
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
    assert not output.exists()


def test_main_writes_the_results_table(tmp_path: Path) -> None:
    letters = tmp_path / "letters"
    letters.mkdir()
    for suffix in (".txt", ".expected.json"):
        (letters / f"006_two_amounts_statement{suffix}").write_text(
            STATEMENT.with_suffix(suffix).read_text(encoding="utf-8"), encoding="utf-8"
        )
    output = tmp_path / "RESULTS.md"
    llm = FakeLLM(statement_responses())
    assert main(output=output, letters_dir=letters, client_factory=lambda: llm) == 0
    assert "| 006_two_amounts_statement | ok | 1/1 | 2/2 | 0/0 | 0 | 0 | 3 |" in output.read_text(encoding="utf-8")
