from pathlib import Path
from typing import Any

import pytest

from letterbox.schema import Fact, LetterFacts
from letterbox.verify import CHECK_WITH_SENDER, FactStatus, verify

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"
LETTER_PATHS = sorted(LETTERS_DIR.glob("*.txt"))
LETTER = (LETTERS_DIR / "006_two_amounts_statement.txt").read_text(encoding="utf-8")
MADE_UP_QUOTE = "You may skip this payment without any charge."


def fact(**fields: Any) -> Fact:
    return Fact.model_validate(fields)


def facts(*items: Fact) -> LetterFacts:
    return LetterFacts(facts=list(items))


SENDER = fact(kind="sender", value="Harbourview Credit Union", evidence="Harbourview Credit Union")
MINIMUM = fact(kind="amount", label="minimum payment", value="$75.00", evidence="Your minimum payment is $75.00.")


@pytest.mark.parametrize("letter", LETTER_PATHS, ids=lambda p: p.stem)
def test_every_answer_key_verifies_fully(letter: Path) -> None:
    key = LetterFacts.model_validate_json(letter.with_suffix(".expected.json").read_text(encoding="utf-8"))
    result = verify(key, letter.read_text(encoding="utf-8"))
    assert [checked.fact for checked in result.facts] == key.facts
    assert all(checked.status is FactStatus.VERIFIED for checked in result.facts)
    assert result.dropped == []


def test_made_up_quote_on_an_action_drops_just_that_fact() -> None:
    action = fact(kind="required_action", value="Skip this payment.", evidence=MADE_UP_QUOTE)
    result = verify(facts(SENDER, action, MINIMUM), LETTER)
    assert [checked.fact for checked in result.facts] == [SENDER, MINIMUM]
    assert result.dropped == [action]


def test_made_up_quote_on_a_deadline_is_marked_not_sure() -> None:
    deadline = fact(kind="deadline", value="January 5, 2027", evidence="Payment is due on January 5, 2027.")
    result = verify(facts(deadline), LETTER)
    assert result.facts[0].status is FactStatus.NOT_SURE
    assert result.dropped == []


def test_real_quote_with_the_wrong_amount_is_marked_not_sure() -> None:
    wrong = fact(kind="amount", label="minimum payment", value="$57.00", evidence="Your minimum payment is $75.00.")
    result = verify(facts(SENDER, wrong), LETTER)
    assert result.facts[1].fact == wrong
    assert result.facts[1].status is FactStatus.NOT_SURE
    assert result.facts[0].status is FactStatus.VERIFIED


def test_real_quote_with_the_wrong_deadline_is_marked_not_sure() -> None:
    wrong = fact(kind="deadline", value="December 15, 2026", evidence="The minimum payment is due on December 5, 2026.")
    assert verify(facts(wrong), LETTER).facts[0].status is FactStatus.NOT_SURE


def test_not_sure_fact_shows_check_with_sender_instead_of_its_value() -> None:
    wrong = fact(kind="amount", value="$57.00", evidence="Your minimum payment is $75.00.")
    checked = verify(facts(wrong), LETTER).facts[0]
    assert checked.display_value == CHECK_WITH_SENDER == "not sure, check with the sender"


def test_verified_fact_shows_its_value() -> None:
    assert verify(facts(MINIMUM), LETTER).facts[0].display_value == "$75.00"


def test_evidence_split_across_lines_still_verifies() -> None:
    letter = "The fine for this violation is\n$65.00.   Pay it soon."
    fine = fact(kind="amount", value="$65.00", evidence="The fine for this violation is $65.00.")
    assert verify(facts(fine), letter).facts[0].status is FactStatus.VERIFIED


RENT_LETTER = (LETTERS_DIR / "002_rent_increase.txt").read_text(encoding="utf-8")


def test_real_quote_with_the_wrong_date_is_marked_not_sure() -> None:
    wrong = fact(kind="date", label="new rent takes effect", value="March 1, 2027", evidence="The new rent takes effect on February 1, 2027.")
    result = verify(facts(wrong), RENT_LETTER)
    assert result.facts[0].status is FactStatus.NOT_SURE
    assert result.facts[0].display_value == CHECK_WITH_SENDER


def test_made_up_quote_on_a_date_is_marked_not_sure() -> None:
    made_up = fact(kind="date", value="January 1, 2027", evidence="The new rent takes effect on January 1, 2027.")
    result = verify(facts(made_up), RENT_LETTER)
    assert result.facts[0].status is FactStatus.NOT_SURE
    assert result.dropped == []


TAX_LETTER = (LETTERS_DIR / "001_tax_reassessment.txt").read_text(encoding="utf-8")
OBJECTION_EVIDENCE = (
    "If you disagree with this reassessment, you may file a notice of objection "
    "within 90 days of the date of this notice."
)


def test_made_up_condition_on_a_real_action_is_marked_not_sure() -> None:
    action = fact(
        kind="required_action",
        condition="you have already paid",
        value="File a notice of objection.",
        evidence=OBJECTION_EVIDENCE,
    )
    result = verify(facts(action), TAX_LETTER)
    assert result.facts[0].status is FactStatus.NOT_SURE
    assert result.facts[0].display_value == CHECK_WITH_SENDER
    assert result.dropped == []


def test_real_condition_on_a_real_action_verifies() -> None:
    action = fact(
        kind="required_action",
        condition="you disagree with this reassessment",
        value="File a notice of objection.",
        evidence=OBJECTION_EVIDENCE,
    )
    assert verify(facts(action), TAX_LETTER).facts[0].status is FactStatus.VERIFIED


def test_made_up_quote_on_a_conditional_action_is_still_dropped() -> None:
    action = fact(
        kind="required_action",
        condition="you disagree with this reassessment",
        value="File a notice of objection.",
        evidence=MADE_UP_QUOTE,
    )
    assert verify(facts(action), TAX_LETTER).dropped == [action]
