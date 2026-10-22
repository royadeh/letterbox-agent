from pathlib import Path

from conftest import FakeLLM
from letterbox.extract import NOT_SURE, NotSure, extract
from letterbox.llm import LLMError
from letterbox.prompts import EXTRACT_SYSTEM_PROMPT
from letterbox.schema import LetterFacts

LETTERS_DIR = Path(__file__).resolve().parent.parent / "data" / "letters"
LETTER = (LETTERS_DIR / "004_document_request.txt").read_text(encoding="utf-8")
GOOD_JSON = (LETTERS_DIR / "004_document_request.expected.json").read_text(encoding="utf-8")
NOT_JSON = "Here are the facts you asked for."
MISSING_EVIDENCE = '{"facts": [{"kind": "amount", "value": "$65.00"}]}'


def test_good_json_is_parsed() -> None:
    llm = FakeLLM([GOOD_JSON])
    result = extract(LETTER, llm)
    assert result == LetterFacts.model_validate_json(GOOD_JSON)
    assert len(llm.calls) == 1


def test_bad_json_then_good_json_retries_once_and_succeeds() -> None:
    llm = FakeLLM([NOT_JSON, GOOD_JSON])
    result = extract(LETTER, llm)
    assert isinstance(result, LetterFacts)
    assert len(llm.calls) == 2


def test_bad_json_twice_returns_not_sure_after_exactly_two_calls() -> None:
    llm = FakeLLM([NOT_JSON, NOT_JSON])
    result = extract(LETTER, llm)
    assert isinstance(result, NotSure)
    assert result.message == NOT_SURE == "I'm not sure"
    assert len(llm.calls) == 2


def test_json_that_fails_the_schema_counts_as_bad() -> None:
    llm = FakeLLM([MISSING_EVIDENCE, MISSING_EVIDENCE])
    assert isinstance(extract(LETTER, llm), NotSure)
    assert len(llm.calls) == 2


def test_failed_model_call_counts_as_a_failed_attempt() -> None:
    llm = FakeLLM([LLMError("refused"), GOOD_JSON])
    assert isinstance(extract(LETTER, llm), LetterFacts)
    assert len(llm.calls) == 2


def test_json_inside_a_code_fence_is_accepted() -> None:
    llm = FakeLLM([f"```json\n{GOOD_JSON}\n```"])
    assert isinstance(extract(LETTER, llm), LetterFacts)
    assert len(llm.calls) == 1


def test_letter_and_system_prompt_are_sent() -> None:
    llm = FakeLLM([GOOD_JSON])
    extract(LETTER, llm)
    assert llm.calls[0].system == EXTRACT_SYSTEM_PROMPT
    assert LETTER in llm.calls[0].user


def test_retry_tells_the_model_its_answer_was_not_valid() -> None:
    llm = FakeLLM([NOT_JSON, GOOD_JSON])
    extract(LETTER, llm)
    assert LETTER in llm.calls[1].user
    assert "not valid" in llm.calls[1].user
