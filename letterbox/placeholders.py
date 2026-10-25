"""Placeholders such as {F2}: the model writes them, the code fills in the values.

Shared by the explain, options and reply steps, so the model never writes a
deadline, amount or date itself.
"""

import json
import re
from typing import Callable

from letterbox.verify import CheckedFact, FactStatus, VerifiedFacts

CHECK_WITH_SENDER_FA = "مطمئن نیستیم، با فرستنده بررسی کنید"
PLACEHOLDER = re.compile(r"\{(F\d+)\}")
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
ValueOf = Callable[[CheckedFact], str]


def number_facts(verified: VerifiedFacts) -> NumberedFacts:
    return {f"F{number}": checked for number, checked in enumerate(verified.facts, start=1)}


def describe_all(facts: NumberedFacts) -> str:
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


def placeholders(text: str) -> set[str]:
    return set(PLACEHOLDER.findall(text))


def check_known(where: str, text: str, facts: NumberedFacts) -> None:
    unknown = placeholders(text) - facts.keys()
    if unknown:
        raise ValueError(f"{where}: unknown placeholders {sorted(unknown)}.")


def check_own_words(where: str, text: str) -> None:
    """The model's own words, outside placeholders, must hold no numbers or dates."""
    own_words = PLACEHOLDER.sub(" ", text)
    if DIGIT.search(own_words):
        raise ValueError(f"{where}: write numbers only as placeholders.")
    if ENGLISH_MONTH.search(own_words) or FARSI_MONTHS.intersection(re.findall(r"\w+", own_words)):
        raise ValueError(f"{where}: write dates only as placeholders.")


def fill(text: str, facts: NumberedFacts, value_of: ValueOf) -> str:
    return PLACEHOLDER.sub(lambda match: value_of(facts[match.group(1)]), text)


def english_value(checked: CheckedFact) -> str:
    return checked.display_value


def farsi_value(checked: CheckedFact) -> str:
    value = CHECK_WITH_SENDER_FA if checked.status is FactStatus.NOT_SURE else checked.fact.value
    return f"{FIRST_STRONG_ISOLATE}{value}{POP_DIRECTIONAL_ISOLATE}"
