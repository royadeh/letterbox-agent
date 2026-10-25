import socket
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from letterbox.schema import FactKind, LetterFacts
from letterbox.verify import VerifiedFacts, verify

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"
WRONG_TAX_DEADLINE = "April 30, 2027"


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


def tax_letter_verified() -> VerifiedFacts:
    """Letter 001's facts, with the payment deadline (F5) wrong so it is marked not sure.

    F1 sender, F2 reference, F3 purpose, F4 amount, F5 deadline (not sure),
    F6 relative deadline, F7 action, F8 conditional action.
    """
    letter = LETTERS_DIR / "001_tax_reassessment.txt"
    key = LetterFacts.model_validate_json(letter.with_suffix(".expected.json").read_text(encoding="utf-8"))
    facts = [
        fact.model_copy(update={"value": WRONG_TAX_DEADLINE}) if fact.value == "March 31, 2027" else fact
        for fact in key.facts
    ]
    assert [fact.kind for fact in facts][4] is FactKind.DEADLINE
    return verify(LetterFacts(facts=facts), letter.read_text(encoding="utf-8"))
