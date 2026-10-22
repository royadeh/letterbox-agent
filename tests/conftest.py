import socket
from dataclasses import dataclass, field
from typing import Any

import pytest


@dataclass(frozen=True)
class Call:
    system: str
    user: str


@dataclass
class FakeLLM:
    """Returns canned responses in order and records every call.

    A response that is an exception is raised instead of returned.
    """

    responses: list[str | Exception]
    calls: list[Call] = field(default_factory=list)

    def complete(self, system: str, user: str) -> str:
        self.calls.append(Call(system=system, user=user))
        assert len(self.calls) <= len(self.responses), "FakeLLM ran out of responses"
        response = self.responses[len(self.calls) - 1]
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture(autouse=True)
def no_api_key_or_network(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("Tests must not use the network.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
