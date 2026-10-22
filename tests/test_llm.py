from types import SimpleNamespace
from typing import Any

import pytest

from letterbox import llm
from letterbox.llm import API_KEY_ENV, MODEL, ClaudeClient, LLMError, response_text


class RecordingAnthropic:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


def make_response(stop_reason: str, *blocks: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop_reason, content=list(blocks))


def text_block(text: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=text)


def test_model_is_claude_sonnet_5_5() -> None:
    assert MODEL == "claude-sonnet-5-5"


def test_client_without_key_in_environment_is_rejected() -> None:
    with pytest.raises(LLMError):
        ClaudeClient()


def test_client_reads_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "test-key-not-real")
    monkeypatch.setattr(llm.anthropic, "Anthropic", RecordingAnthropic)
    client = ClaudeClient()
    assert client.sdk.kwargs == {"api_key": "test-key-not-real"}


def test_response_text_joins_text_blocks_and_skips_thinking() -> None:
    thinking = SimpleNamespace(type="thinking", thinking="")
    response = make_response("end_turn", thinking, text_block('{"facts"'), text_block(": []}"))
    assert response_text(response) == '{"facts": []}'


@pytest.mark.parametrize("stop_reason", ["refusal", "max_tokens"])
def test_unfinished_response_is_an_error(stop_reason: str) -> None:
    with pytest.raises(LLMError):
        response_text(make_response(stop_reason, text_block("{")))


def test_response_without_text_is_an_error() -> None:
    with pytest.raises(LLMError):
        response_text(make_response("end_turn"))
