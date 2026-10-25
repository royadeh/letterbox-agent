import copy
import json

import pytest

from conftest import MADE_UP_CONDITION, WRONG_TAX_DEADLINE, FakeLLM, tax_letter_verified
from letterbox.extract import NotSure
from letterbox.options import Options, list_options
from letterbox.prompts import OPTIONS_SYSTEM_PROMPT
from letterbox.schema import Fact, LetterFacts
from letterbox.verify import CHECK_WITH_SENDER, verify

VERIFIED = tax_letter_verified()
FARSI_CONDITION = "با این ارزیابی دوباره موافق نیستید"

GOOD_OPTIONS: list[dict[str, str]] = [
    {"fact": "F7", "english": "Pay the full balance by {F5}.", "farsi": "کل مبلغ را تا {F5} بپردازید."},
    {
        "fact": "F8",
        "english": "File a notice of objection {F6}.",
        "farsi": "اعتراض‌نامه را {F6} ثبت کنید.",
        "farsi_condition": FARSI_CONDITION,
    },
]


def answer(options: list[dict[str, str]]) -> str:
    return json.dumps({"options": options}, ensure_ascii=False)


def edited(index: int, **changes: str) -> str:
    options = copy.deepcopy(GOOD_OPTIONS)
    options[index].update(changes)
    return answer(options)


def without_farsi_condition() -> str:
    options = copy.deepcopy(GOOD_OPTIONS)
    del options[1]["farsi_condition"]
    return answer(options)


GOOD = answer(GOOD_OPTIONS)


def isolate(text: str) -> str:
    return f"⁨{text}⁩"


def test_good_answer_lists_each_action_and_shows_its_condition() -> None:
    llm = FakeLLM([GOOD])
    result = list_options(VERIFIED, llm)
    assert isinstance(result, Options)
    assert result.english == (
        f"Pay the full balance by {CHECK_WITH_SENDER}.\n"
        "If you disagree with this reassessment: "
        "File a notice of objection within 90 days of the date of this notice."
    )
    assert result.farsi.splitlines()[1] == (
        f"اگر {FARSI_CONDITION}: اعتراض‌نامه را {isolate('within 90 days of the date of this notice')} ثبت کنید."
    )
    assert len(llm.calls) == 1


def test_not_sure_value_is_never_shown_or_sent_to_the_model() -> None:
    llm = FakeLLM([GOOD])
    result = list_options(VERIFIED, llm)
    assert isinstance(result, Options)
    assert WRONG_TAX_DEADLINE not in result.english + result.farsi
    assert WRONG_TAX_DEADLINE not in llm.calls[0].user


def test_system_prompt_and_actions_are_sent() -> None:
    llm = FakeLLM([GOOD])
    list_options(VERIFIED, llm)
    assert llm.calls[0].system == OPTIONS_SYSTEM_PROMPT
    assert "Pay the full balance." in llm.calls[0].user
    assert "you disagree with this reassessment" in llm.calls[0].user


BAD_ANSWERS = {
    "not json": "Your options are below.",
    "option for a fact that is not an action": answer(
        [*GOOD_OPTIONS, {"fact": "F3", "english": "Ask for a review.", "farsi": "درخواست بازبینی کنید."}]
    ),
    "missing action": answer(GOOD_OPTIONS[:1]),
    "duplicate action": answer([*GOOD_OPTIONS, GOOD_OPTIONS[0]]),
    "conditional action without farsi condition": without_farsi_condition(),
    "farsi condition on an unconditional action": edited(0, farsi_condition=FARSI_CONDITION),
    "number written by the model": edited(0, english="Pay the full balance of $1,284.50 by {F5}."),
    "persian digits in the farsi condition": edited(1, farsi_condition="اگر تا ۹۰ روز موافق نیستید"),
    "month name": edited(0, english="Pay the full balance by March: {F5}."),
    "farsi placeholders differ": edited(0, farsi="کل مبلغ را بپردازید."),
    "unknown placeholder": edited(0, english="Pay {F9} by {F5}.", farsi="{F9} را تا {F5} بپردازید."),
    "english stronger than the letter": edited(0, english="You need to pay the full balance by {F5}."),
    "farsi stronger than the letter": edited(0, farsi="شما مجبور هستید کل مبلغ را تا {F5} بپردازید."),
}


@pytest.mark.parametrize("bad", BAD_ANSWERS.values(), ids=BAD_ANSWERS.keys())
def test_invalid_answer_is_retried_once(bad: str) -> None:
    llm = FakeLLM([bad, GOOD])
    assert isinstance(list_options(VERIFIED, llm), Options)
    assert len(llm.calls) == 2


def test_invalid_answer_twice_returns_not_sure_after_exactly_two_calls() -> None:
    bad = BAD_ANSWERS["missing action"]
    llm = FakeLLM([bad, bad])
    result = list_options(VERIFIED, llm)
    assert isinstance(result, NotSure)
    assert len(llm.calls) == 2


def test_no_verified_actions_gives_no_options_without_calling_the_model() -> None:
    only_sender = LetterFacts(
        facts=[Fact(kind="sender", value="Greenfield Transit Authority", evidence="Greenfield Transit Authority")]
    )
    llm = FakeLLM([])
    result = list_options(verify(only_sender, "Greenfield Transit Authority"), llm)
    assert result == Options(items=[])
    assert llm.calls == []


# F8's condition is made up, so verify marks the action not sure.
NOT_SURE_ACTION = tax_letter_verified(condition=MADE_UP_CONDITION)
NOT_SURE_OPTIONS: list[dict[str, str]] = [
    GOOD_OPTIONS[0],
    {"fact": "F8", "english": "Another step may apply: {F8}.", "farsi": "ممکن است کار دیگری هم لازم باشد: {F8}."},
]


def test_not_sure_action_is_listed_as_check_with_sender_without_its_condition() -> None:
    llm = FakeLLM([answer(NOT_SURE_OPTIONS)])
    result = list_options(NOT_SURE_ACTION, llm)
    assert isinstance(result, Options)
    assert result.english.splitlines()[1] == f"Another step may apply: {CHECK_WITH_SENDER}."
    assert MADE_UP_CONDITION not in result.english
    assert MADE_UP_CONDITION not in llm.calls[0].user
    assert "File a notice of objection." not in llm.calls[0].user


NOT_SURE_BAD_ANSWERS = {
    "farsi condition on a not-sure action": answer(
        [NOT_SURE_OPTIONS[0], {**NOT_SURE_OPTIONS[1], "farsi_condition": FARSI_CONDITION}]
    ),
    "not-sure action without its placeholder": answer(
        [NOT_SURE_OPTIONS[0], {"fact": "F8", "english": "File an objection.", "farsi": "اعتراض کنید."}]
    ),
}


@pytest.mark.parametrize("bad", NOT_SURE_BAD_ANSWERS.values(), ids=NOT_SURE_BAD_ANSWERS.keys())
def test_invalid_answer_for_a_not_sure_action_is_retried_once(bad: str) -> None:
    llm = FakeLLM([bad, answer(NOT_SURE_OPTIONS)])
    assert isinstance(list_options(NOT_SURE_ACTION, llm), Options)
    assert len(llm.calls) == 2


def test_by_is_dropped_before_a_deadline_that_starts_with_within() -> None:
    by_within = edited(1, english="File a notice of objection by {F6}.", farsi="اعتراض‌نامه را تا {F6} ثبت کنید.")
    result = list_options(VERIFIED, FakeLLM([by_within]))
    assert isinstance(result, Options)
    assert result.english.splitlines()[1] == (
        "If you disagree with this reassessment: File a notice of objection within 90 days of the date of this notice."
    )
    assert f"اعتراض‌نامه را {isolate('within 90 days of the date of this notice')} ثبت کنید." in result.farsi
