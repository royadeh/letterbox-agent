import copy
import json
from pathlib import Path
from typing import Any

import pytest

from conftest import FakeLLM
from letterbox.explain import CHECK_WITH_SENDER_FA, Explanation, explain
from letterbox.extract import NotSure
from letterbox.prompts import EXPLAIN_SYSTEM_PROMPT
from letterbox.schema import Fact, LetterFacts
from letterbox.verify import CHECK_WITH_SENDER, VerifiedFacts, verify

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"
LETTER = (LETTERS_DIR / "006_two_amounts_statement.txt").read_text(encoding="utf-8")
WRONG_DEADLINE = "December 15, 2026"


def fact(**fields: Any) -> Fact:
    return Fact.model_validate(fields)


# F1 sender (verified), F2 amount (verified), F3 deadline (wrong value, so not sure)
VERIFIED = verify(
    LetterFacts(
        facts=[
            fact(kind="sender", value="Harbourview Credit Union", evidence="Harbourview Credit Union"),
            fact(kind="amount", label="minimum payment", value="$75.00", evidence="Your minimum payment is $75.00."),
            fact(
                kind="deadline",
                label="minimum payment is due",
                value=WRONG_DEADLINE,
                evidence="The minimum payment is due on December 5, 2026.",
            ),
        ]
    ),
    LETTER,
)

GOOD_ITEMS: list[dict[str, str]] = [
    {"fact": "F1", "english": "This letter is from {F1}.", "farsi": "این نامه از طرف {F1} است."},
    {"fact": "F2", "english": "Your minimum payment is {F2}.", "farsi": "حداقل پرداخت شما {F2} است."},
    {"fact": "F3", "english": "When the minimum payment is due: {F3}.", "farsi": "مهلت حداقل پرداخت: {F3}."},
]


def answer(items: list[dict[str, str]]) -> str:
    return json.dumps({"items": items}, ensure_ascii=False)


def edited(index: int, **changes: str) -> str:
    items = copy.deepcopy(GOOD_ITEMS)
    items[index].update(changes)
    return answer(items)


GOOD = answer(GOOD_ITEMS)


def isolate(text: str) -> str:
    return f"⁨{text}⁩"


def test_good_answer_gives_english_then_farsi_explanation() -> None:
    llm = FakeLLM([GOOD])
    result = explain(VERIFIED, llm)
    assert isinstance(result, Explanation)
    assert result.english == (
        "This letter is from Harbourview Credit Union.\n"
        "Your minimum payment is $75.00.\n"
        f"When the minimum payment is due: {CHECK_WITH_SENDER}."
    )
    assert result.farsi == (
        f"این نامه از طرف {isolate('Harbourview Credit Union')} است.\n"
        f"حداقل پرداخت شما {isolate('$75.00')} است.\n"
        f"مهلت حداقل پرداخت: {isolate(CHECK_WITH_SENDER_FA)}."
    )
    assert len(llm.calls) == 1


def test_farsi_not_sure_wording() -> None:
    assert CHECK_WITH_SENDER_FA == "مطمئن نیستیم، با فرستنده بررسی کنید"


def test_not_sure_value_is_never_shown_or_sent_to_the_model() -> None:
    llm = FakeLLM([GOOD])
    result = explain(VERIFIED, llm)
    assert isinstance(result, Explanation)
    assert WRONG_DEADLINE not in result.english
    assert WRONG_DEADLINE not in result.farsi
    assert WRONG_DEADLINE not in llm.calls[0].user


def test_verified_values_and_system_prompt_are_sent() -> None:
    llm = FakeLLM([GOOD])
    explain(VERIFIED, llm)
    assert llm.calls[0].system == EXPLAIN_SYSTEM_PROMPT
    assert "$75.00" in llm.calls[0].user
    assert "F3" in llm.calls[0].user


BAD_ANSWERS = {
    "not json": "Here is your explanation.",
    "number written in english": edited(1, english="Your minimum payment is {F2}, about $75."),
    "persian digits in farsi": edited(1, farsi="حداقل پرداخت شما {F2}، یعنی ۷۵ دلار، است."),
    "added deadline in english": edited(0, english="This letter is from {F1}. Pay within 10 days."),
    "english month name": edited(2, english="Pay by December: {F3}."),
    "farsi month name": edited(2, farsi="مهلت حداقل پرداخت در دسامبر: {F3}."),
    "missing fact": answer(GOOD_ITEMS[:2]),
    "duplicate fact": answer([*GOOD_ITEMS, GOOD_ITEMS[0]]),
    "unknown fact": answer([*GOOD_ITEMS, {"fact": "F4", "english": "Call a lawyer.", "farsi": "با وکیل تماس بگیرید."}]),
    "unknown placeholder": edited(0, english="This letter is from {F1} {F9}.", farsi="این نامه از طرف {F1} {F9} است."),
    "farsi placeholders differ": edited(1, farsi="حداقل پرداخت شما مشخص شده است."),
    "amount without its placeholder": edited(1, english="Your minimum payment is shown.", farsi="حداقل پرداخت شما مشخص شده است."),
    "not-sure deadline without its placeholder": edited(2, english="The payment is due soon.", farsi="مهلت پرداخت نزدیک است."),
}


@pytest.mark.parametrize("bad", BAD_ANSWERS.values(), ids=BAD_ANSWERS.keys())
def test_invalid_answer_is_retried_once(bad: str) -> None:
    llm = FakeLLM([bad, GOOD])
    assert isinstance(explain(VERIFIED, llm), Explanation)
    assert len(llm.calls) == 2


def test_invalid_answer_twice_returns_not_sure_after_exactly_two_calls() -> None:
    bad = BAD_ANSWERS["number written in english"]
    llm = FakeLLM([bad, bad])
    result = explain(VERIFIED, llm)
    assert isinstance(result, NotSure)
    assert result.message == "I'm not sure"
    assert len(llm.calls) == 2


def test_no_verified_facts_returns_not_sure_without_calling_the_model() -> None:
    llm = FakeLLM([])
    result = explain(VerifiedFacts(facts=[], dropped=[]), llm)
    assert isinstance(result, NotSure)
    assert llm.calls == []
