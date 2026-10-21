"""Pydantic models for facts taken from a letter."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator


class FactKind(str, Enum):
    SENDER = "sender"
    REFERENCE = "reference"
    PURPOSE = "purpose"
    AMOUNT = "amount"
    DEADLINE = "deadline"
    DATE = "date"
    REQUIRED_ACTION = "required_action"


LABELLED_KINDS = frozenset({FactKind.AMOUNT, FactKind.DEADLINE, FactKind.DATE})
CONDITIONAL_KINDS = frozenset({FactKind.REQUIRED_ACTION})


class Fact(BaseModel):
    """One fact from a letter, with the exact sentence that supports it.

    Values are text copied from the letter. Amounts and dates are never
    converted to numbers or calendar dates.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: FactKind
    value: StrictStr
    evidence: StrictStr
    label: StrictStr | None = None
    condition: StrictStr | None = None

    @field_validator("value", "evidence", "label", "condition")
    @classmethod
    def _not_blank(cls, text: str | None) -> str | None:
        if text is not None and not text.strip():
            raise ValueError("must not be blank")
        return text

    @model_validator(mode="after")
    def _optional_fields_fit_kind(self) -> "Fact":
        if self.label is not None and self.kind not in LABELLED_KINDS:
            raise ValueError(f"label is not allowed on {self.kind.value} facts")
        if self.condition is not None and self.kind not in CONDITIONAL_KINDS:
            raise ValueError(f"condition is not allowed on {self.kind.value} facts")
        return self


class LetterFacts(BaseModel):
    """All facts taken from one letter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    facts: list[Fact] = Field(min_length=1)
