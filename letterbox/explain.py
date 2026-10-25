"""Explain step: verified facts -> plain-language explanation in English, then Farsi.

The model never writes values itself. It writes placeholders such as {F2}, and
the code fills in the exact value from the letter, or the "check with the
sender" note for a fact marked not sure.
"""

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from letterbox.answers import NotSure, ask_with_one_retry
from letterbox.llm import LLMClient
from letterbox.placeholders import (
    CHECK_WITH_SENDER_FA,
    NumberedFacts,
    check_known,
    check_own_words,
    describe_all,
    english_value,
    farsi_value,
    fill,
    is_not_sure,
    number_facts,
    placeholders,
)
from letterbox.prompts import EXPLAIN_SYSTEM_PROMPT, explain_user_message
from letterbox.schema import FactKind
from letterbox.verify import VerifiedFacts

__all__ = ["CHECK_WITH_SENDER_FA", "Explanation", "explain"]

PLACEHOLDER_KINDS = frozenset({FactKind.AMOUNT, FactKind.DEADLINE, FactKind.DATE, FactKind.REFERENCE})


class DraftItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact: StrictStr
    english: StrictStr
    farsi: StrictStr

    @field_validator("english", "farsi")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("must not be blank")
        return text


class Draft(BaseModel):
    """The model's answer, still with placeholders."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[DraftItem] = Field(min_length=1)


class ExplainedFact(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str
    english: str
    farsi: str


class Explanation(BaseModel):
    """The finished explanation, with every value filled in by code."""

    model_config = ConfigDict(frozen=True)

    items: list[ExplainedFact]

    @property
    def english(self) -> str:
        return "\n".join(item.english for item in self.items)

    @property
    def farsi(self) -> str:
        return "\n".join(item.farsi for item in self.items)


def explain(verified: VerifiedFacts, client: LLMClient) -> Explanation | NotSure:
    facts = number_facts(verified)
    if not facts:
        return NotSure(reason="No verified facts to explain.")

    def parse(text: str) -> Explanation:
        return _render(_check(Draft.model_validate_json(text), facts), facts)

    return ask_with_one_retry(client, EXPLAIN_SYSTEM_PROMPT, explain_user_message(describe_all(facts)), parse)


def _check(draft: Draft, facts: NumberedFacts) -> Draft:
    _check_one_item_per_fact(draft, facts)
    for item in draft.items:
        _check_placeholders(item, facts)
        check_own_words(item.fact, item.english)
        check_own_words(item.fact, item.farsi)
    return draft


def _check_one_item_per_fact(draft: Draft, facts: NumberedFacts) -> None:
    ids = [item.fact for item in draft.items]
    if sorted(ids) != sorted(facts):
        raise ValueError(f"Write exactly one item for each of {list(facts)}; got {ids}.")


def _check_placeholders(item: DraftItem, facts: NumberedFacts) -> None:
    english = placeholders(item.english)
    if english != placeholders(item.farsi):
        raise ValueError(f"{item.fact}: English and Farsi must use the same placeholders.")
    check_known(item.fact, item.english, facts)
    checked = facts[item.fact]
    if (checked.fact.kind in PLACEHOLDER_KINDS or is_not_sure(checked)) and item.fact not in english:
        raise ValueError(f"{item.fact}: must contain the placeholder {{{item.fact}}}.")


def _render(draft: Draft, facts: NumberedFacts) -> Explanation:
    return Explanation(
        items=[
            ExplainedFact(
                fact_id=item.fact,
                english=fill(item.english, facts, english_value),
                farsi=fill(item.farsi, facts, farsi_value),
            )
            for item in draft.items
        ]
    )
