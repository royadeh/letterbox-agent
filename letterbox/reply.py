"""Reply step: an English reply draft, with a Farsi explanation of what it says.

The reply must not admit fault, promise payment, or add facts. Values come
only from placeholders; a not-sure value becomes a bracketed note the reader
must resolve with the sender before sending.
"""

import re

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator

from letterbox.answers import NotSure, ask_with_one_retry
from letterbox.llm import LLMClient
from letterbox.placeholders import (
    NumberedFacts,
    check_known,
    check_sender_name,
    check_text_not_stronger,
    check_own_words,
    describe_all,
    english_unconfirmed,
    farsi_unconfirmed,
    farsi_value,
    fill,
    number_facts,
    placeholders,
)
from letterbox.prompts import REPLY_SYSTEM_PROMPT, facts_user_message
from letterbox.schema import FactKind
from letterbox.verify import CHECK_WITH_SENDER, CheckedFact, FactStatus, VerifiedFacts

# Phrases that admit fault or promise payment. A list cannot catch every
# wording, so the eval must also check replies with the real model.
FAULT_OR_PROMISE = re.compile(
    r"\b(i|we)\s+(will|shall|promise to|agree to|commit to|undertake to)\s+"
    r"(pay|repay|settle|send\s+(the\s+|my\s+|our\s+|a\s+)?payment|make\s+(the\s+|my\s+|our\s+|a\s+)?payment)\b"
    r"|\b(i|we)\s+(promise|admit|owe|apologi[sz]e)\b"
    r"|\b(i|we)\s+accept\s+(the\s+)?(responsibility|blame|debt|charge|claim)\b"
    r"|\b(i\s+am|i'm|we\s+are|we're)\s+(sorry|at\s+fault|responsible)\b"
    r"|\b(my|our)\s+(fault|mistake|error)\b",
    re.IGNORECASE,
)
# The reply stays neutral: it does not accept, reject or dispute the claim.
NOT_NEUTRAL = re.compile(
    r"\b(i|we)\s+(do\s+not\s+|don['’]t\s+|cannot\s+|can['’]t\s+|can\s+not\s+)?"
    r"(accept|agree|disagree|dispute|reject|contest|deny|object|challenge|refuse)\b",
    re.IGNORECASE,
)


class Draft(BaseModel):
    """The model's answer, still with placeholders."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reply: StrictStr
    farsi_explanation: StrictStr

    @field_validator("reply", "farsi_explanation")
    @classmethod
    def _not_blank(cls, text: str) -> str:
        if not text.strip():
            raise ValueError("must not be blank")
        return text


class Reply(BaseModel):
    """The finished reply draft, with every value filled in by code."""

    model_config = ConfigDict(frozen=True)

    english: str
    farsi_explanation: str


def draft_reply(verified: VerifiedFacts, client: LLMClient) -> Reply | NotSure:
    facts = number_facts(verified)
    if not facts:
        return NotSure(error_type="NoVerifiedFacts")

    def parse(text: str) -> Reply:
        return _render(_check(Draft.model_validate_json(text), facts), facts)

    return ask_with_one_retry(client, REPLY_SYSTEM_PROMPT, facts_user_message(describe_all(facts)), parse)


def _check(draft: Draft, facts: NumberedFacts) -> Draft:
    for where, text in (("reply", draft.reply), ("farsi_explanation", draft.farsi_explanation)):
        check_known(where, text, facts)
        check_sender_name(where, text, facts)
        check_own_words(where, text)
    check_text_not_stronger("farsi_explanation", draft.farsi_explanation, facts)
    match = FAULT_OR_PROMISE.search(draft.reply)
    if match:
        raise ValueError(f"reply: do not admit fault or promise payment ({match.group(0)!r}).")
    match = NOT_NEUTRAL.search(draft.reply)
    if match:
        raise ValueError(f"reply: stay neutral; do not accept, reject or dispute the claim ({match.group(0)!r}).")
    _check_reference(draft, facts)
    return draft


def _check_reference(draft: Draft, facts: NumberedFacts) -> None:
    references = {fact_id for fact_id, checked in facts.items() if checked.fact.kind is FactKind.REFERENCE}
    if references and not references & placeholders(draft.reply):
        raise ValueError(f"reply: give the letter's reference with its placeholder, one of {sorted(references)}.")


def _render(draft: Draft, facts: NumberedFacts) -> Reply:
    return Reply(
        english=fill(draft.reply, facts, _reply_value, _reply_note),
        farsi_explanation=fill(draft.farsi_explanation, facts, farsi_value, farsi_unconfirmed),
    )


def _reply_note(kind: FactKind) -> str:
    """In the reply, notes are in brackets: the reader must resolve them before sending."""
    return f"[{english_unconfirmed(kind)}]"


def _reply_value(checked: CheckedFact) -> str:
    if checked.status is FactStatus.NOT_SURE:
        return f"[{CHECK_WITH_SENDER}]"
    return checked.fact.value
