"""Options step: the reader's options, built only from verified required actions.

A conditional action always shows its condition: the code puts the condition,
copied from the letter, in front of the option. An action marked not sure (its
condition was not in its sentence) is listed as "check with the sender".
"""

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator

from letterbox.answers import NotSure, ask_with_one_retry
from letterbox.llm import LLMClient
from letterbox.placeholders import (
    NumberedFacts,
    check_known,
    check_not_stronger,
    check_own_words,
    describe_all,
    english_unconfirmed,
    english_value,
    farsi_unconfirmed,
    farsi_value,
    fill,
    is_not_sure,
    number_facts,
    placeholders,
)
from letterbox.prompts import OPTIONS_SYSTEM_PROMPT, facts_user_message
from letterbox.schema import FactKind
from letterbox.verify import CheckedFact, VerifiedFacts


class DraftOption(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fact: StrictStr
    english: StrictStr
    farsi: StrictStr
    farsi_condition: StrictStr | None = None

    @field_validator("english", "farsi", "farsi_condition")
    @classmethod
    def _not_blank(cls, text: str | None) -> str | None:
        if text is not None and not text.strip():
            raise ValueError("must not be blank")
        return text


class Draft(BaseModel):
    """The model's answer, still with placeholders."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    options: list[DraftOption]


class Option(BaseModel):
    model_config = ConfigDict(frozen=True)

    fact_id: str
    english: str
    farsi: str


class Options(BaseModel):
    """The finished options, with conditions and values filled in by code."""

    model_config = ConfigDict(frozen=True)

    items: list[Option]

    @property
    def english(self) -> str:
        return "\n".join(item.english for item in self.items)

    @property
    def farsi(self) -> str:
        return "\n".join(item.farsi for item in self.items)


def list_options(verified: VerifiedFacts, client: LLMClient) -> Options | NotSure:
    facts = number_facts(verified)
    actions = _action_ids(facts)
    if not actions:
        return Options(items=[])

    def parse(text: str) -> Options:
        return _render(_check(Draft.model_validate_json(text), facts, actions), facts)

    return ask_with_one_retry(client, OPTIONS_SYSTEM_PROMPT, facts_user_message(describe_all(facts)), parse)


def _action_ids(facts: NumberedFacts) -> list[str]:
    return [fact_id for fact_id, checked in facts.items() if checked.fact.kind is FactKind.REQUIRED_ACTION]


def _shown_condition(checked: CheckedFact) -> str | None:
    """The condition to show, or None. A not-sure action's condition is never shown."""
    return None if is_not_sure(checked) else checked.fact.condition


def _check(draft: Draft, facts: NumberedFacts, actions: list[str]) -> Draft:
    ids = [option.fact for option in draft.options]
    if sorted(ids) != sorted(actions):
        raise ValueError(f"Write exactly one option for each of {actions}; got {ids}.")
    for option in draft.options:
        _check_condition(option, facts)
        _check_option_text(option, facts)
    return draft


def _check_condition(option: DraftOption, facts: NumberedFacts) -> None:
    has_condition = _shown_condition(facts[option.fact]) is not None
    if has_condition and option.farsi_condition is None:
        raise ValueError(f"{option.fact}: this action has a condition; give it in farsi_condition.")
    if not has_condition and option.farsi_condition is not None:
        raise ValueError(f"{option.fact}: this action has no condition; leave out farsi_condition.")


def _check_option_text(option: DraftOption, facts: NumberedFacts) -> None:
    english = placeholders(option.english)
    if english != placeholders(option.farsi):
        raise ValueError(f"{option.fact}: English and Farsi must use the same placeholders.")
    if is_not_sure(facts[option.fact]) and option.fact not in english:
        raise ValueError(f"{option.fact}: this action is not sure; write only its placeholder {{{option.fact}}}.")
    farsi = f"{option.farsi} {option.farsi_condition or ''}"
    check_not_stronger(option.fact, facts[option.fact], option.english, farsi)
    for text in (option.english, option.farsi, option.farsi_condition or ""):
        check_known(option.fact, text, facts)
        check_own_words(option.fact, text)


def _render(draft: Draft, facts: NumberedFacts) -> Options:
    return Options(items=[_render_option(option, facts) for option in draft.options])


def _render_option(option: DraftOption, facts: NumberedFacts) -> Option:
    english = fill(option.english, facts, english_value, english_unconfirmed)
    farsi = fill(option.farsi, facts, farsi_value, farsi_unconfirmed)
    condition = _shown_condition(facts[option.fact])
    if condition is not None and option.farsi_condition is not None:
        english = f"If {condition}: {english}"
        farsi = f"اگر {fill(option.farsi_condition, facts, farsi_value, farsi_unconfirmed)}: {farsi}"
    return Option(fact_id=option.fact, english=english, farsi=farsi)
