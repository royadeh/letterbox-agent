"""Extract step: letter -> model -> validated facts, or "I'm not sure"."""

from pydantic import BaseModel, ConfigDict, ValidationError

from letterbox.llm import LLMClient, LLMError
from letterbox.prompts import EXTRACT_SYSTEM_PROMPT, extract_user_message, retry_user_message
from letterbox.schema import LetterFacts

NOT_SURE = "I'm not sure"


class NotSure(BaseModel):
    """The model's answer could not be used, even after one retry."""

    model_config = ConfigDict(frozen=True)

    message: str = NOT_SURE
    reason: str


def extract(letter: str, client: LLMClient) -> LetterFacts | NotSure:
    """Ask the model for the letter's facts; retry once if the answer is invalid."""
    first = _attempt(client, extract_user_message(letter))
    if isinstance(first, LetterFacts):
        return first
    second = _attempt(client, retry_user_message(letter, first))
    if isinstance(second, LetterFacts):
        return second
    return NotSure(reason=second)


def _attempt(client: LLMClient, user: str) -> LetterFacts | str:
    """Return the parsed facts, or the reason the answer was not valid."""
    try:
        text = client.complete(EXTRACT_SYSTEM_PROMPT, user)
        return LetterFacts.model_validate_json(_strip_code_fence(text))
    except (LLMError, ValidationError) as error:
        return str(error)


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)
