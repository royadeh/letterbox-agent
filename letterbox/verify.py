"""Verify step: check every extracted fact against the letter it came from."""

from enum import Enum

from pydantic import BaseModel, ConfigDict

from letterbox.schema import Fact, FactKind, LetterFacts
from letterbox.text import appears_in

CHECK_WITH_SENDER = "not sure, check with the sender"
NEVER_GUESS_KINDS = frozenset({FactKind.DEADLINE, FactKind.AMOUNT})


class FactStatus(str, Enum):
    VERIFIED = "verified"
    NOT_SURE = "not_sure"


class CheckedFact(BaseModel):
    """A fact and the result of checking it.

    A not-sure fact keeps the model's answer for the record, but its value
    must not be shown to the reader: use `display_value`.
    """

    model_config = ConfigDict(frozen=True)

    fact: Fact
    status: FactStatus

    @property
    def display_value(self) -> str:
        if self.status is FactStatus.NOT_SURE:
            return CHECK_WITH_SENDER
        return self.fact.value


class VerifiedFacts(BaseModel):
    """Facts that passed or were marked not sure, plus the facts that were dropped."""

    model_config = ConfigDict(frozen=True)

    facts: list[CheckedFact]
    dropped: list[Fact]


def verify(extraction: LetterFacts, letter: str) -> VerifiedFacts:
    checked: list[CheckedFact] = []
    dropped: list[Fact] = []
    for fact in extraction.facts:
        if _is_supported(fact, letter):
            checked.append(CheckedFact(fact=fact, status=FactStatus.VERIFIED))
        elif fact.kind in NEVER_GUESS_KINDS:
            checked.append(CheckedFact(fact=fact, status=FactStatus.NOT_SURE))
        else:
            dropped.append(fact)
    return VerifiedFacts(facts=checked, dropped=dropped)


def _is_supported(fact: Fact, letter: str) -> bool:
    if not appears_in(fact.evidence, letter):
        return False
    if fact.kind in NEVER_GUESS_KINDS:
        return appears_in(fact.value, fact.evidence)
    return True
