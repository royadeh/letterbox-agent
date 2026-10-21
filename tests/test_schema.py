from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from letterbox.schema import Fact, FactKind, LetterFacts


def make_fact(**overrides: Any) -> Fact:
    fields: dict[str, Any] = {
        "kind": "amount",
        "value": "$1,284.50",
        "evidence": "As a result, you owe a balance of $1,284.50.",
    }
    fields.update(overrides)
    return Fact.model_validate(fields)


def test_valid_fact_parses() -> None:
    fact = make_fact()
    assert fact.kind is FactKind.AMOUNT
    assert fact.label is None
    assert fact.condition is None


def test_fact_without_evidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Fact.model_validate({"kind": "amount", "value": "$1,284.50"})


@pytest.mark.parametrize("evidence", ["", "   ", "\n\t"])
def test_fact_with_blank_evidence_is_rejected(evidence: str) -> None:
    with pytest.raises(ValidationError):
        make_fact(evidence=evidence)


def test_blank_value_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_fact(value=" ")


def test_amount_is_kept_as_copied_text() -> None:
    assert make_fact(value="$1,284.50").value == "$1,284.50"


@pytest.mark.parametrize("value", [1284.5, 1284, Decimal("1284.50")])
def test_amount_given_as_a_number_is_rejected(value: Any) -> None:
    with pytest.raises(ValidationError):
        make_fact(value=value)


def test_deadline_is_kept_as_copied_text() -> None:
    fact = make_fact(
        kind="deadline",
        value="within 30 days of the date of this letter",
        evidence="You must send these documents within 30 days of the date of this letter.",
    )
    assert fact.value == "within 30 days of the date of this letter"


def test_deadline_given_as_a_date_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_fact(kind="deadline", value=date(2027, 3, 31))


def test_label_is_optional_on_amount_deadline_and_date() -> None:
    for kind in ("amount", "deadline", "date"):
        assert make_fact(kind=kind, label="balance owing").label == "balance owing"


def test_label_is_rejected_on_other_kinds() -> None:
    with pytest.raises(ValidationError):
        make_fact(kind="purpose", label="balance owing")


def test_blank_label_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_fact(label="  ")


def test_condition_is_optional_on_required_action() -> None:
    fact = make_fact(
        kind="required_action",
        value="Ask about a payment arrangement.",
        condition="you are having trouble paying",
        evidence="If you are having trouble paying, you can ask us about a payment arrangement.",
    )
    assert fact.condition == "you are having trouble paying"


def test_condition_is_rejected_on_other_kinds() -> None:
    with pytest.raises(ValidationError):
        make_fact(condition="you are having trouble paying")


def test_date_kind_exists_for_non_deadline_dates() -> None:
    fact = make_fact(
        kind="date",
        label="new rent takes effect",
        value="February 1, 2027",
        evidence="The new rent takes effect on February 1, 2027.",
    )
    assert fact.kind is FactKind.DATE


def test_unknown_kind_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_fact(kind="guess")


def test_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        make_fact(confidence="high")


def test_letter_facts_needs_at_least_one_fact() -> None:
    with pytest.raises(ValidationError):
        LetterFacts.model_validate({"facts": []})
