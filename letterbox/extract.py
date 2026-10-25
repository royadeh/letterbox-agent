"""Extract step: letter -> model -> validated facts, or "I'm not sure"."""

from letterbox.answers import NOT_SURE, NotSure, ask_with_one_retry
from letterbox.llm import LLMClient
from letterbox.prompts import EXTRACT_SYSTEM_PROMPT, extract_user_message
from letterbox.schema import LetterFacts

__all__ = ["NOT_SURE", "NotSure", "extract"]


def extract(letter: str, client: LLMClient) -> LetterFacts | NotSure:
    """Ask the model for the letter's facts; retry once if the answer is invalid."""
    return ask_with_one_retry(
        client, EXTRACT_SYSTEM_PROMPT, extract_user_message(letter), LetterFacts.model_validate_json
    )
