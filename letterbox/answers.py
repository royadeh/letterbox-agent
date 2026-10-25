"""Shared handling of model answers: parse, retry once, then "I'm not sure"."""

from dataclasses import dataclass
from typing import Callable, TypeVar

from pydantic import BaseModel, ConfigDict

from letterbox.llm import LLMClient, LLMError
from letterbox.prompts import retry_user_message

NOT_SURE = "I'm not sure"

T = TypeVar("T")


class NotSure(BaseModel):
    """The model's answer could not be used, even after one retry.

    Holds only the error type and the number of attempts, never the model's
    answer or letter text, so it is safe to log.
    """

    model_config = ConfigDict(frozen=True)

    message: str = NOT_SURE
    error_type: str
    attempts: int = 0


@dataclass(frozen=True)
class _Invalid:
    reason: str  # sent back to the model on retry; never logged
    error_type: str


def ask_with_one_retry(client: LLMClient, system: str, user: str, parse: Callable[[str], T]) -> T | NotSure:
    """Ask the model; if `parse` rejects the answer, ask once more and say why."""
    first = _attempt(client, system, user, parse)
    if not isinstance(first, _Invalid):
        return first
    second = _attempt(client, system, retry_user_message(user, first.reason), parse)
    if not isinstance(second, _Invalid):
        return second
    return NotSure(error_type=second.error_type, attempts=2)


def _attempt(client: LLMClient, system: str, user: str, parse: Callable[[str], T]) -> T | _Invalid:
    try:
        return parse(strip_code_fence(client.complete(system, user)))
    except (LLMError, ValueError) as error:
        return _Invalid(reason=str(error), error_type=type(error).__name__)


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)
