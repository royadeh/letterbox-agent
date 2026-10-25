"""Explain step: verified facts -> plain-language explanation in English, then Farsi.

The model never writes values itself. It writes placeholders such as {F2}, and
the code fills in the exact value from the letter, or the "check with the
sender" note for a fact marked not sure.
"""

import json
import re
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from letterbox.answers import NotSure, ask_with_one_retry
from letterbox.llm import LLMClient
from letterbox.prompts import EXPLAIN_SYSTEM_PROMPT, explain_user_message
from letterbox.schema import FactKind
from letterbox.verify import CheckedFact, FactStatus, VerifiedFacts

CHECK_WITH_SENDER_FA = "مطمئن نیستیم، با فرستنده بررسی کنید"
PLACEHOLDER = re.compile(r"\{(F\d+)\}")
PLACEHOLDER_KINDS = frozenset({FactKind.AMOUNT, FactKind.DEADLINE, FactKind.DATE, FactKind.REFERENCE})
DIGIT = re.compile(r"\d")  # Unicode-aware: also matches Persian and Arabic-Indic digits
ENGLISH_MONTH = re.compile(
    r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\b"
)
# Gregorian and Persian month names. Words that are also everyday Persian words
# (مه, تیر, مهر, آذر, دی) are left out; a date that uses them has digits anyway.
FARSI_MONTHS = frozenset(
    {
        "ژانویه", "فوریه", "مارس", "آوریل", "ژوئن", "ژوئیه", "جولای", "اوت", "آگوست",
        "سپتامبر", "اکتبر", "نوامبر", "دسامبر",
        "فروردین", "اردیبهشت", "خرداد", "مرداد", "شهریور", "آبان", "بهمن", "اسفند",
    }
)
# Keeps a left-to-right value such as "$75.00" in the right order inside Farsi text.
FIRST_STRONG_ISOLATE = "⁨"
POP_DIRECTIONAL_ISOLATE = "⁩"

NumberedFacts = dict[str, CheckedFact]


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

    return ask_with_one_retry(client, EXPLAIN_SYSTEM_PROMPT, explain_user_message(_describe_all(facts)), parse)


def number_facts(verified: VerifiedFacts) -> NumberedFacts:
    return {f"F{number}": checked for number, checked in enumerate(verified.facts, start=1)}


def _describe_all(facts: NumberedFacts) -> str:
    return json.dumps([_describe(fact_id, checked) for fact_id, checked in facts.items()], ensure_ascii=False, indent=2)


def _describe(fact_id: str, checked: CheckedFact) -> dict[str, str]:
    """What the model sees. A not-sure fact's value is never sent."""
    fact = checked.fact
    entry = {"id": fact_id, "kind": fact.kind.value}
    if fact.label:
        entry["label"] = fact.label
    if checked.status is FactStatus.NOT_SURE:
        entry["status"] = "not sure"
    else:
        entry["value"] = fact.value
    if fact.condition:
        entry["condition"] = fact.condition
    return entry


def _check(draft: Draft, facts: NumberedFacts) -> Draft:
    _check_one_item_per_fact(draft, facts)
    for item in draft.items:
        _check_placeholders(item, facts)
        _check_own_words(item.fact, item.english)
        _check_own_words(item.fact, item.farsi)
    return draft


def _check_one_item_per_fact(draft: Draft, facts: NumberedFacts) -> None:
    ids = [item.fact for item in draft.items]
    if sorted(ids) != sorted(facts):
        raise ValueError(f"Write exactly one item for each of {list(facts)}; got {ids}.")


def _check_placeholders(item: DraftItem, facts: NumberedFacts) -> None:
    english, farsi = _placeholders(item.english), _placeholders(item.farsi)
    if english != farsi:
        raise ValueError(f"{item.fact}: English and Farsi must use the same placeholders.")
    unknown = english - facts.keys()
    if unknown:
        raise ValueError(f"{item.fact}: unknown placeholders {sorted(unknown)}.")
    if facts[item.fact].fact.kind in PLACEHOLDER_KINDS and item.fact not in english:
        raise ValueError(f"{item.fact}: must contain the placeholder {{{item.fact}}}.")


def _check_own_words(fact_id: str, text: str) -> None:
    own_words = PLACEHOLDER.sub(" ", text)
    if DIGIT.search(own_words):
        raise ValueError(f"{fact_id}: write numbers only as placeholders.")
    if ENGLISH_MONTH.search(own_words) or FARSI_MONTHS.intersection(re.findall(r"\w+", own_words)):
        raise ValueError(f"{fact_id}: write dates only as placeholders.")


def _placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def _render(draft: Draft, facts: NumberedFacts) -> Explanation:
    return Explanation(
        items=[
            ExplainedFact(
                fact_id=item.fact,
                english=_fill(item.english, facts, _english_value),
                farsi=_fill(item.farsi, facts, _farsi_value),
            )
            for item in draft.items
        ]
    )


def _fill(text: str, facts: NumberedFacts, value_of: Callable[[CheckedFact], str]) -> str:
    return PLACEHOLDER.sub(lambda match: value_of(facts[match.group(1)]), text)


def _english_value(checked: CheckedFact) -> str:
    return checked.display_value


def _farsi_value(checked: CheckedFact) -> str:
    value = CHECK_WITH_SENDER_FA if checked.status is FactStatus.NOT_SURE else checked.fact.value
    return f"{FIRST_STRONG_ISOLATE}{value}{POP_DIRECTIONAL_ISOLATE}"
