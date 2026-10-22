from letterbox.prompts import EXTRACT_SYSTEM_PROMPT, extract_user_message


def test_prompt_asks_for_exact_supporting_sentences() -> None:
    assert "exact sentence" in EXTRACT_SYSTEM_PROMPT.lower()


def test_prompt_says_never_to_calculate_dates() -> None:
    assert "never calculate dates" in EXTRACT_SYSTEM_PROMPT.lower()


def test_user_message_wraps_the_letter_in_tags() -> None:
    message = extract_user_message("Dear Tenant, rent is going up.")
    assert "<letter>\nDear Tenant, rent is going up.\n</letter>" in message
