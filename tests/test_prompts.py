import pytest

from letterbox.prompts import (
    EXPLAIN_SYSTEM_PROMPT,
    EXTRACT_SYSTEM_PROMPT,
    OPTIONS_SYSTEM_PROMPT,
    REPLY_SYSTEM_PROMPT,
    explain_user_message,
    extract_user_message,
)


def test_prompt_asks_for_exact_supporting_sentences() -> None:
    assert "exact sentence" in EXTRACT_SYSTEM_PROMPT.lower()


def test_prompt_says_never_to_calculate_dates() -> None:
    assert "never calculate dates" in EXTRACT_SYSTEM_PROMPT.lower()


def test_user_message_wraps_the_letter_in_tags() -> None:
    message = extract_user_message("Dear Tenant, rent is going up.")
    assert "<letter>\nDear Tenant, rent is going up.\n</letter>" in message


def test_explain_prompt_allows_only_the_given_facts() -> None:
    assert "use only the facts" in EXPLAIN_SYSTEM_PROMPT.lower()


def test_explain_prompt_says_never_to_write_numbers_or_dates() -> None:
    assert "never write a number, date or month name yourself" in EXPLAIN_SYSTEM_PROMPT.lower()


def test_explain_user_message_wraps_the_facts_in_tags() -> None:
    assert explain_user_message('[{"id": "F1"}]') == '<facts>\n[{"id": "F1"}]\n</facts>'


def test_options_prompt_asks_for_one_option_per_required_action() -> None:
    assert "one option for each required_action fact" in OPTIONS_SYSTEM_PROMPT.lower()


@pytest.mark.parametrize("prompt", ["options", "reply"])
def test_options_and_reply_prompts_say_never_to_write_numbers_or_dates(prompt: str) -> None:
    text = {"options": OPTIONS_SYSTEM_PROMPT, "reply": REPLY_SYSTEM_PROMPT}[prompt]
    assert "never write a number, date or month name yourself" in text.lower()


def test_reply_prompt_forbids_admitting_fault_promising_payment_and_new_facts() -> None:
    text = REPLY_SYSTEM_PROMPT.lower()
    assert "do not admit fault" in text
    assert "do not promise payment" in text
    assert "do not add any fact" in text


@pytest.mark.parametrize("prompt", ["explain", "options"])
def test_explain_and_options_prompts_say_not_to_strengthen_the_letter(prompt: str) -> None:
    text = {"explain": EXPLAIN_SYSTEM_PROMPT, "options": OPTIONS_SYSTEM_PROMPT}[prompt].lower()
    assert "do not make the letter sound stronger than it is" in text
    assert "the letter asks you to" in text


def test_reply_prompt_asks_for_a_neutral_reply() -> None:
    text = REPLY_SYSTEM_PROMPT.lower()
    assert "do not say that the reader accepts, rejects or disputes" in text
    assert "explanation" in text and "documents" in text


@pytest.mark.parametrize("prompt", ["explain", "options", "reply"])
def test_prompts_say_never_to_translate_the_senders_name(prompt: str) -> None:
    text = {"explain": EXPLAIN_SYSTEM_PROMPT, "options": OPTIONS_SYSTEM_PROMPT, "reply": REPLY_SYSTEM_PROMPT}[prompt].lower()
    assert "never translate or transliterate the sender's name" in text


def test_reply_prompt_says_the_explanation_describes_no_admission_not_non_acceptance() -> None:
    explanation_rules = REPLY_SYSTEM_PROMPT.split("The Farsi explanation", 1)[1]
    assert "does not admit any mistake or debt" in explanation_rules
    assert "اقرار نمی‌شود" in explanation_rules
    assert "does not accept" not in explanation_rules
    assert "نمی‌پذیر" in explanation_rules  # named only as wording to avoid
