import json

import pytest

from conftest import LETTERS_DIR, WRONG_TAX_DEADLINE, FakeLLM, tax_letter_verified
from letterbox.explain import CHECK_WITH_SENDER_FA
from letterbox.extract import NotSure
from letterbox.prompts import REPLY_SYSTEM_PROMPT
from letterbox.reply import Reply, draft_reply
from letterbox.schema import Fact, LetterFacts
from letterbox.verify import VerifiedFacts, verify

VERIFIED = tax_letter_verified()

GOOD_REPLY = (
    "Dear {F1},\n\n"
    "Re: {F2}\n\n"
    "Thank you for your letter. Please confirm the date by which the balance must be paid: {F5}.\n"
    "I would like to understand the reassessment before I decide what to do.\n\n"
    "Sincerely,\n[Your name]"
)
GOOD_FARSI = (
    "این پیش‌نویس به {F1} می‌گوید که نامه را با شماره مرجع {F2} دریافت کرده‌اید "
    "و از آن‌ها می‌خواهد مهلت پرداخت را تأیید کنند: {F5}. "
    "در این نامه نه اشتباهی را می‌پذیرید و نه قول پرداخت می‌دهید."
)


def answer(reply: str = GOOD_REPLY, farsi: str = GOOD_FARSI) -> str:
    return json.dumps({"reply": reply, "farsi_explanation": farsi}, ensure_ascii=False)


GOOD = answer()


def isolate(text: str) -> str:
    return f"⁨{text}⁩"


def test_good_answer_gives_english_reply_with_values_filled_in() -> None:
    llm = FakeLLM([GOOD])
    result = draft_reply(VERIFIED, llm)
    assert isinstance(result, Reply)
    assert result.english == (
        "Dear Northfield Revenue Office,\n\n"
        "Re: TEST-REF-001\n\n"
        "Thank you for your letter. Please confirm the date by which the balance must be paid: "
        "[not sure, check with the sender].\n"
        "I would like to understand the reassessment before I decide what to do.\n\n"
        "Sincerely,\n[Your name]"
    )
    assert isolate("TEST-REF-001") in result.farsi_explanation
    assert isolate(CHECK_WITH_SENDER_FA) in result.farsi_explanation
    assert len(llm.calls) == 1


def test_not_sure_value_is_never_shown_or_sent_to_the_model() -> None:
    llm = FakeLLM([GOOD])
    result = draft_reply(VERIFIED, llm)
    assert isinstance(result, Reply)
    assert WRONG_TAX_DEADLINE not in result.english + result.farsi_explanation
    assert WRONG_TAX_DEADLINE not in llm.calls[0].user


def test_system_prompt_is_sent() -> None:
    llm = FakeLLM([GOOD])
    draft_reply(VERIFIED, llm)
    assert llm.calls[0].system == REPLY_SYSTEM_PROMPT


BAD_ANSWERS = {
    "not json": "Dear Sir or Madam, ...",
    "promises payment": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I will pay the full balance.")),
    "promises to make a payment": answer(reply=GOOD_REPLY + "\nWe will make the payment soon."),
    "admits a mistake": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "This was my mistake.")),
    "admits owing": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I owe the balance.")),
    "apologises": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I apologize for the error.")),
    "number written by the model": answer(reply=GOOD_REPLY.replace("{F2}", "{F2} and $1,284.50")),
    "month name": answer(reply=GOOD_REPLY.replace("Thank you", "In March, thank you")),
    "persian digits in farsi": answer(farsi=GOOD_FARSI + " ۹۰ روز"),
    "unknown placeholder": answer(reply=GOOD_REPLY.replace("{F1}", "{F9}")),
    "missing reference placeholder": answer(reply=GOOD_REPLY.replace("Re: {F2}\n\n", "")),
    "farsi name in parentheses after the sender": answer(farsi=GOOD_FARSI.replace("به {F1} می‌گوید", "به {F1} (اداره درآمد نورث‌فیلد) می‌گوید")),
    "does not accept": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I do not accept the reassessment.")),
    "don't accept, curly apostrophe": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I don\u2019t accept this.")),
    "disputes": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I dispute this claim.")),
    "disagrees": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I disagree with the reassessment.")),
    "rejects": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "We reject the balance.")),
    "accepts": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I accept the reassessment.")),
    "agrees": answer(reply=GOOD_REPLY.replace("Thank you for your letter.", "I agree with your decision.")),
}


@pytest.mark.parametrize("bad", BAD_ANSWERS.values(), ids=BAD_ANSWERS.keys())
def test_invalid_answer_is_retried_once(bad: str) -> None:
    llm = FakeLLM([bad, GOOD])
    assert isinstance(draft_reply(VERIFIED, llm), Reply)
    assert len(llm.calls) == 2


def test_invalid_answer_twice_returns_not_sure_after_exactly_two_calls() -> None:
    bad = BAD_ANSWERS["promises payment"]
    llm = FakeLLM([bad, bad])
    result = draft_reply(VERIFIED, llm)
    assert isinstance(result, NotSure)
    assert len(llm.calls) == 2


def test_reply_without_a_reference_fact_needs_no_reference_placeholder() -> None:
    sender = Fact(kind="sender", value="Greenfield Transit Authority", evidence="Greenfield Transit Authority")
    verified = verify(LetterFacts(facts=[sender]), "Greenfield Transit Authority")
    reply = "Dear {F1},\n\nThank you for your letter.\n\nSincerely,\n[Your name]"
    llm = FakeLLM([answer(reply=reply, farsi="این پیش‌نویس از {F1} تشکر می‌کند.")])
    assert isinstance(draft_reply(verified, llm), Reply)


def test_no_verified_facts_returns_not_sure_without_calling_the_model() -> None:
    llm = FakeLLM([])
    assert isinstance(draft_reply(VerifiedFacts(facts=[], dropped=[]), llm), NotSure)
    assert llm.calls == []


def test_neutral_reply_asking_for_explanation_documents_and_deadlines_is_accepted() -> None:
    neutral = (
        "Dear {F1},\n\nRe: {F2}\n\n"
        "Thank you for your letter. Please send me an explanation of the reassessment and copies of the "
        "documents you used. Please also confirm the deadlines in your letter: {F5} and {F6}.\n\n"
        "Sincerely,\n[Your name]"
    )
    assert isinstance(draft_reply(VERIFIED, FakeLLM([answer(reply=neutral)])), Reply)


def test_not_sure_deadline_after_by_in_the_reply_becomes_a_bracketed_note() -> None:
    reply = "Dear {F1},\n\nRe: {F2}\n\nI understand the balance is due by {F5}. Please confirm it.\n\n[Your name]"
    result = draft_reply(VERIFIED, FakeLLM([answer(reply=reply)]))
    assert isinstance(result, Reply)
    assert (
        "I understand the balance is due. [The deadline is not confirmed: check with the sender.] Please confirm it."
        in result.english
    )
    assert WRONG_TAX_DEADLINE not in result.english


@pytest.mark.parametrize(
    "farsi",
    [
        "این پیش‌نویس می‌گوید شما باید {F6} اعتراض کنید.",
        "این پیش‌نویس می‌گوید لازم است مدارک را بفرستید.",
        "این پیش‌نویس می‌گوید شما مجبور هستید پاسخ دهید.",
        "This draft says you must reply.",
    ],
)
def test_reply_explanation_stronger_than_the_letter_is_retried(farsi: str) -> None:
    llm = FakeLLM([answer(farsi=farsi), GOOD])
    assert isinstance(draft_reply(VERIFIED, llm), Reply)
    assert len(llm.calls) == 2


UTILITY = LETTERS_DIR / "003_utility_disconnection.txt"


def test_reply_explanation_may_use_strong_wording_for_a_fact_the_letter_states_strongly() -> None:
    key = LetterFacts.model_validate_json(UTILITY.with_suffix(".expected.json").read_text(encoding="utf-8"))
    verified = verify(key, UTILITY.read_text(encoding="utf-8"))
    reply = "Dear {F1},\n\nRe: {F2}\n\nThank you for your letter.\n\nSincerely,\n[Your name]"
    farsi = "نامه می‌گوید باید مبلغ را تا {F5} بپردازید."  # F5: "you must pay the overdue amount by ..."
    llm = FakeLLM([answer(reply=reply, farsi=farsi)])
    assert isinstance(draft_reply(verified, llm), Reply)
    assert len(llm.calls) == 1
