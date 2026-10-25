"""Placeholders such as {F2}: the model writes them, the code fills in the values.

Shared by the explain, options and reply steps, so the model never writes a
deadline, amount or date itself.
"""

import json
import re
from typing import Callable

from letterbox.schema import FactKind
from letterbox.verify import NEVER_GUESS_KINDS, CheckedFact, FactStatus, VerifiedFacts

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
# A placeholder, and an English or Farsi preposition before it. "by" is dropped
# before a value that already starts with "within", so the reader never sees
# "by within". A not-sure deadline, amount or date is never placed after a
# preposition: it is taken out and a "not confirmed" note follows the sentence.
FILL = re.compile(
    r"(?P<before>(?<!\w)(?P<word>by|before|until|no later than|of|on|تا|قبل از|در)\s+)?\{(?P<id>F\d+)\}",
    re.IGNORECASE,
)
BY_WORDS = frozenset({"by", "before", "until", "no later than", "تا", "قبل از"})
NOTE_MARK = "\x00"
SENTENCE_END = re.compile(r"[.!?؟](?=\s|$)")
SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+(?=[.,;:!?،؛؟])")
NOT_CONFIRMED_EN = {FactKind.DEADLINE: "deadline", FactKind.AMOUNT: "amount", FactKind.DATE: "date"}
NOT_CONFIRMED_FA = {FactKind.DEADLINE: "مهلت", FactKind.AMOUNT: "مبلغ", FactKind.DATE: "تاریخ"}
# Wording that makes the letter sound stronger, allowed only if the letter's own
# sentence for that fact uses such wording.
STRONG_ENGLISH = re.compile(r"\b(must|needs?\s+to|ha(?:ve|s)\s+to|required\s+to|obliged\s+to|obligated\s+to)\b", re.IGNORECASE)
STRONG_FARSI = ("باید", "مجبور", "لازم است", "ملزم", "موظف")
# Keeps a left-to-right value such as "$75.00" in the right order inside Farsi text.
FIRST_STRONG_ISOLATE = "⁨"
POP_DIRECTIONAL_ISOLATE = "⁩"

NumberedFacts = dict[str, CheckedFact]
ValueOf = Callable[[CheckedFact], str]
NoteOf = Callable[[FactKind], str]


def number_facts(verified: VerifiedFacts) -> NumberedFacts:
    return {f"F{number}": checked for number, checked in enumerate(verified.facts, start=1)}


def describe_all(facts: NumberedFacts) -> str:
    return json.dumps([_describe(fact_id, checked) for fact_id, checked in facts.items()], ensure_ascii=False, indent=2)


def _describe(fact_id: str, checked: CheckedFact) -> dict[str, str]:
    """What the model sees. A not-sure fact's value and condition are never sent."""
    fact = checked.fact
    entry = {"id": fact_id, "kind": fact.kind.value}
    if fact.label:
        entry["label"] = fact.label
    if checked.status is FactStatus.NOT_SURE:
        entry["status"] = "not sure"
        return entry
    entry["value"] = fact.value
    if fact.condition:
        entry["condition"] = fact.condition
    if letter_is_strong(checked):
        entry["strong_wording"] = "yes"
    return entry


def letter_is_strong(checked: CheckedFact) -> bool:
    """True if the letter's own (verified) sentence says "must", "need to" or similar."""
    return checked.status is FactStatus.VERIFIED and STRONG_ENGLISH.search(checked.fact.evidence) is not None


def check_not_stronger(where: str, checked: CheckedFact, english: str, farsi: str) -> None:
    if letter_is_strong(checked):
        return
    if STRONG_ENGLISH.search(english) or any(word in farsi for word in STRONG_FARSI):
        raise ValueError(
            f"{where}: this sounds stronger than the letter; do not write 'must', 'need to' or 'have to', "
            "write 'the letter asks you to'."
        )


def is_not_sure(checked: CheckedFact) -> bool:
    return checked.status is FactStatus.NOT_SURE


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


def fill(text: str, facts: NumberedFacts, value_of: ValueOf, note_of: NoteOf) -> str:
    notes: list[str] = []

    def replace(match: re.Match[str]) -> str:
        checked = facts[match.group("id")]
        before = match.group("before") or ""
        if before and _is_unconfirmed_value(checked):
            notes.append(note_of(checked.fact.kind))
            return NOTE_MARK
        if before and match.group("word").lower() in BY_WORDS and _starts_with_within(checked):
            before = ""
        return f"{before}{value_of(checked)}"

    return _place_notes(FILL.sub(replace, text), notes)


def _place_notes(text: str, notes: list[str]) -> str:
    """Put each note after the end of the sentence its placeholder was taken from."""
    if not notes:
        return text
    for note in notes:
        start = text.index(NOTE_MARK)
        rest = text[start + 1 :]
        end = SENTENCE_END.search(rest)
        if end is None:
            text = f"{text[:start]}{rest.rstrip()}. {note}"
        else:
            text = f"{text[:start]}{rest[: end.end()]} {note}{rest[end.end():]}"
    return SPACE_BEFORE_PUNCTUATION.sub("", re.sub(r"(?<=\S)[ \t]{2,}", " ", text))


def _is_unconfirmed_value(checked: CheckedFact) -> bool:
    return checked.status is FactStatus.NOT_SURE and checked.fact.kind in NEVER_GUESS_KINDS


def english_unconfirmed(kind: FactKind) -> str:
    return f"The {NOT_CONFIRMED_EN[kind]} is not confirmed: check with the sender."


def farsi_unconfirmed(kind: FactKind) -> str:
    return f"{NOT_CONFIRMED_FA[kind]} تأیید نشده است: با فرستنده بررسی کنید."


def _starts_with_within(checked: CheckedFact) -> bool:
    return checked.status is FactStatus.VERIFIED and checked.fact.value.strip().lower().startswith("within")


def english_value(checked: CheckedFact) -> str:
    return checked.display_value


def farsi_value(checked: CheckedFact) -> str:
    value = CHECK_WITH_SENDER_FA if checked.status is FactStatus.NOT_SURE else checked.fact.value
    return f"{FIRST_STRONG_ISOLATE}{value}{POP_DIRECTIONAL_ISOLATE}"
