"""Model clients: the interface the pipeline uses, and the real Claude client."""

import os
from typing import Any, Protocol

import anthropic

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 16000
API_KEY_ENV = "ANTHROPIC_API_KEY"
UNFINISHED_STOP_REASONS = frozenset({"refusal", "max_tokens"})


class LLMError(Exception):
    """The model gave no usable answer."""


class LLMClient(Protocol):
    def complete(self, system: str, user: str) -> str: ...


class ClaudeClient:
    """Calls Claude. The API key is read from the environment only."""

    def __init__(self, model: str = MODEL) -> None:
        api_key = os.environ.get(API_KEY_ENV)
        if not api_key:
            raise LLMError(f"Set {API_KEY_ENV} in the environment.")
        self.sdk = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def complete(self, system: str, user: str) -> str:
        response = self.sdk.messages.create(
            model=self.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return response_text(response)


def response_text(response: Any) -> str:
    """Join the text blocks of a finished response."""
    if response.stop_reason in UNFINISHED_STOP_REASONS:
        raise LLMError(f"Model stopped early: {response.stop_reason}")
    text = "".join(block.text for block in response.content if block.type == "text")
    if not text.strip():
        raise LLMError("Model returned no text.")
    return text
