from typing import Any

import pytest

from conftest import LETTERS_DIR
from letterbox.placeholders import (
    check_not_stronger,
    describe_all,
    english_unconfirmed,
    english_value,
    farsi_unconfirmed,
    farsi_value,
    fill,
    number_facts,
)
from letterbox.schema import Fact, FactKind, LetterFacts
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
WRONG_AMOUNT = fact(kind="amount", value="$9.99", evidence="As a result, you owe a balance of $1,284.50.")
WRONG_DATE = fact(kind="date", value="April 1, 2027", evidence="Please pay the full balance by March 31, 2027.")
# F1 relative deadline, F2 fixed deadline, F3 not-sure deadline, F4 not-sure amount, F5 not-sure date
FACTS = number_facts(verify(LetterFacts(facts=[RELATIVE, FIXED, WRONG, WRONG_AMOUNT, WRONG_DATE]), TAX_LETTER))


@pytest.mark.parametrize("word", ["by", "By", "before", "until", "no later than"])
def test_by_is_dropped_before_a_value_that_starts_with_within(word: str) -> None:
    assert fill(f"File it {word} {{F1}}.", FACTS, english_value, english_unconfirmed) == "File it within 90 days of the date of this notice."


def test_by_is_kept_before_a_fixed_date() -> None:
    assert fill("Pay by {F2}.", FACTS, english_value, english_unconfirmed) == "Pay by March 31, 2027."


DEADLINE_NOTE = "The deadline is not confirmed: check with the sender."
AMOUNT_NOTE = "The amount is not confirmed: check with the sender."
DATE_NOTE = "The date is not confirmed: check with the sender."
DEADLINE_NOTE_FA = "مهلت تأیید نشده است: با فرستنده بررسی کنید."


def test_not_confirmed_notes() -> None:
    assert english_unconfirmed(FactKind.DEADLINE) == DEADLINE_NOTE
    assert english_unconfirmed(FactKind.AMOUNT) == AMOUNT_NOTE
    assert english_unconfirmed(FactKind.DATE) == DATE_NOTE
    assert farsi_unconfirmed(FactKind.DEADLINE) == DEADLINE_NOTE_FA
    assert farsi_unconfirmed(FactKind.AMOUNT) == "مبلغ تأیید نشده است: با فرستنده بررسی کنید."
    assert farsi_unconfirmed(FactKind.DATE) == "تاریخ تأیید نشده است: با فرستنده بررسی کنید."


@pytest.mark.parametrize("word", ["by", "of", "on", "before", "until"])
def test_not_sure_deadline_after_a_preposition_becomes_a_note(word: str) -> None:
    result = fill(f"Pay the full balance {word} {{F3}}.", FACTS, english_value, english_unconfirmed)
    assert result == f"Pay the full balance. {DEADLINE_NOTE}"
    assert CHECK_WITH_SENDER not in result


def test_not_sure_amount_and_date_get_their_own_notes() -> None:
    assert fill("Pay the balance of {F4}.", FACTS, english_value, english_unconfirmed) == f"Pay the balance. {AMOUNT_NOTE}"
    assert fill("The rent changes on {F5}.", FACTS, english_value, english_unconfirmed) == f"The rent changes. {DATE_NOTE}"


def test_note_follows_its_own_sentence() -> None:
    result = fill("Pay the full balance by {F3}. Then keep your receipt.", FACTS, english_value, english_unconfirmed)
    assert result == f"Pay the full balance. {DEADLINE_NOTE} Then keep your receipt."


def test_note_is_added_when_the_sentence_has_no_full_stop() -> None:
    result = fill("Pay the full balance by {F3}", FACTS, english_value, english_unconfirmed)
    assert result == f"Pay the full balance. {DEADLINE_NOTE}"


@pytest.mark.parametrize("word", ["تا", "قبل از", "در"])
def test_farsi_not_sure_deadline_after_a_preposition_becomes_a_note(word: str) -> None:
    result = fill(f"کل مبلغ را {word} {{F3}} بپردازید.", FACTS, farsi_value, farsi_unconfirmed)
    assert result == f"کل مبلغ را بپردازید. {DEADLINE_NOTE_FA}"


def test_not_sure_value_without_a_preposition_is_unchanged() -> None:
    result = fill("When the payment is due: {F3}.", FACTS, english_value, english_unconfirmed)
    assert result == f"When the payment is due: {CHECK_WITH_SENDER}."


def test_reply_style_notes_can_be_bracketed() -> None:
    result = fill("Please pay by {F3}.", FACTS, english_value, lambda kind: f"[{english_unconfirmed(kind)}]")
    assert result == f"Please pay. [{DEADLINE_NOTE}]"


@pytest.mark.parametrize("word", ["تا", "قبل از"])
def test_farsi_by_is_dropped_before_a_value_that_starts_with_within(word: str) -> None:
    result = fill(f"آن را {word} {{F1}} ثبت کنید.", FACTS, farsi_value, farsi_unconfirmed)
    assert result == "آن را ⁨within 90 days of the date of this notice⁩ ثبت کنید."


def test_within_without_by_is_unchanged() -> None:
    assert fill("File it {F1}.", FACTS, english_value, english_unconfirmed) == "File it within 90 days of the date of this notice."


def test_words_ending_in_by_are_not_touched() -> None:
    assert fill("Nearby {F1}.", FACTS, english_value, english_unconfirmed) == "Nearby within 90 days of the date of this notice."


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
