from typing import Any

import pytest

from conftest import LETTERS_DIR
from letterbox.placeholders import (
    check_not_stronger,
    describe_all,
    english_value,
    farsi_value,
    fill,
    number_facts,
)
from letterbox.schema import Fact, LetterFacts
from letterbox.verify import CHECK_WITH_SENDER, verify

TAX_LETTER = (LETTERS_DIR / "001_tax_reassessment.txt").read_text(encoding="utf-8")
UTILITY = LETTERS_DIR / "003_utility_disconnection.txt"


def fact(**fields: Any) -> Fact:
    return Fact.model_validate(fields)


RELATIVE = fact(
    kind="deadline",
    value="within 90 days of the date of this notice",
    evidence="If you disagree with this reassessment, you may file a notice of objection within 90 days of the date of this notice.",
)
FIXED = fact(kind="deadline", value="March 31, 2027", evidence="Please pay the full balance by March 31, 2027.")
WRONG = fact(kind="deadline", value="April 30, 2027", evidence="Please pay the full balance by March 31, 2027.")
# F1 relative deadline, F2 fixed deadline, F3 not-sure deadline
FACTS = number_facts(verify(LetterFacts(facts=[RELATIVE, FIXED, WRONG]), TAX_LETTER))


@pytest.mark.parametrize("word", ["by", "By", "before", "until", "no later than"])
def test_by_is_dropped_before_a_value_that_starts_with_within(word: str) -> None:
    assert fill(f"File it {word} {{F1}}.", FACTS, english_value) == "File it within 90 days of the date of this notice."


def test_by_is_kept_before_a_fixed_date() -> None:
    assert fill("Pay by {F2}.", FACTS, english_value) == "Pay by March 31, 2027."


def test_by_is_kept_before_a_not_sure_value() -> None:
    assert fill("Pay by {F3}.", FACTS, english_value) == f"Pay by {CHECK_WITH_SENDER}."


@pytest.mark.parametrize("word", ["تا", "قبل از"])
def test_farsi_by_is_dropped_before_a_value_that_starts_with_within(word: str) -> None:
    result = fill(f"آن را {word} {{F1}} ثبت کنید.", FACTS, farsi_value)
    assert result == "آن را ⁨within 90 days of the date of this notice⁩ ثبت کنید."


def test_within_without_by_is_unchanged() -> None:
    assert fill("File it {F1}.", FACTS, english_value) == "File it within 90 days of the date of this notice."


def test_words_ending_in_by_are_not_touched() -> None:
    assert fill("Nearby {F1}.", FACTS, english_value) == "Nearby within 90 days of the date of this notice."


UTILITY_FACTS = number_facts(
    verify(
        LetterFacts.model_validate_json(UTILITY.with_suffix(".expected.json").read_text(encoding="utf-8")),
        UTILITY.read_text(encoding="utf-8"),
    )
)
PAY_OVERDUE = "F6"  # "To avoid disconnection, you must pay the overdue amount by November 15, 2026."
ARRANGEMENT = "F7"  # "If you are having trouble paying, you can ask us about a payment arrangement."


@pytest.mark.parametrize(
    "english, farsi",
    [
        ("You must ask about a payment arrangement.", "درباره ترتیب پرداخت بپرسید."),
        ("You need to ask about a payment arrangement.", "درباره ترتیب پرداخت بپرسید."),
        ("You have to ask about a payment arrangement.", "درباره ترتیب پرداخت بپرسید."),
        ("You are required to ask about a payment arrangement.", "درباره ترتیب پرداخت بپرسید."),
        ("The letter asks you to ask about a payment arrangement.", "باید درباره ترتیب پرداخت بپرسید."),
        ("The letter asks you to ask about a payment arrangement.", "لازم است درباره ترتیب پرداخت بپرسید."),
    ],
)
def test_strong_wording_is_rejected_when_the_letter_does_not_use_it(english: str, farsi: str) -> None:
    with pytest.raises(ValueError, match="stronger than the letter"):
        check_not_stronger(ARRANGEMENT, UTILITY_FACTS[ARRANGEMENT], english, farsi)


def test_strong_wording_is_allowed_when_the_letter_uses_it() -> None:
    check_not_stronger(PAY_OVERDUE, UTILITY_FACTS[PAY_OVERDUE], "You must pay the overdue amount.", "باید مبلغ را بپردازید.")


def test_the_letter_asks_you_to_is_allowed() -> None:
    check_not_stronger(
        ARRANGEMENT, UTILITY_FACTS[ARRANGEMENT], "The letter says you can ask about a payment arrangement.",
        "نامه می‌گوید می‌توانید درباره ترتیب پرداخت بپرسید.",
    )


def test_the_model_is_told_which_facts_use_strong_wording() -> None:
    described = describe_all(UTILITY_FACTS)
    assert '"strong_wording": "yes"' in described
    assert described.count('"strong_wording": "yes"') == 2  # the pay-by deadline sentence and the pay action
