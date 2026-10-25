import json
import logging

import pytest

from conftest import LETTERS_DIR, FakeLLM
from letterbox.graph import READER_NOT_SURE, READER_NOT_SURE_FA, Answer, build_graph, run

LETTER_PATH = LETTERS_DIR / "001_tax_reassessment.txt"
LETTER = LETTER_PATH.read_text(encoding="utf-8")
EXTRACT_OK = LETTER_PATH.with_suffix(".expected.json").read_text(encoding="utf-8")
EXPLAIN_OK = json.dumps(
    {"items": [{"fact": f"F{n}", "english": f"Point: {{F{n}}}.", "farsi": f"نکته: {{F{n}}}."} for n in range(1, 9)]},
    ensure_ascii=False,
)
OPTIONS_OK = json.dumps(
    {
        "options": [
            {"fact": "F7", "english": "Pay the full balance by {F5}.", "farsi": "کل مبلغ را تا {F5} بپردازید."},
            {
                "fact": "F8",
                "english": "File a notice of objection {F6}.",
                "farsi": "اعتراض‌نامه را {F6} ثبت کنید.",
                "farsi_condition": "با این ارزیابی دوباره موافق نیستید",
            },
        ]
    },
    ensure_ascii=False,
)
REPLY_OK = json.dumps(
    {
        "reply": "Dear {F1},\n\nRe: {F2}\n\nThank you for your letter.\n\nSincerely,\n[Your name]",
        "farsi_explanation": "این پیش‌نویس دریافت نامه {F2} را تأیید می‌کند.",
    },
    ensure_ascii=False,
)
BAD = "not json at all"
RUN_ID = "run-test-1"


def run_with(responses: list[str]) -> tuple[Answer, FakeLLM]:
    llm = FakeLLM(list(responses))
    return run(LETTER, llm, run_id=RUN_ID), llm


def not_sure_line(farsi: bool = False) -> str:
    phrase = READER_NOT_SURE_FA if farsi else READER_NOT_SURE
    return f"{phrase} (Reference: {RUN_ID})"


def test_graph_has_the_planned_nodes() -> None:
    nodes = set(build_graph(FakeLLM([])).get_graph().nodes)
    assert {"extract", "verify", "explain", "options", "reply", "finish", "not_sure"} <= nodes


def test_happy_path_runs_every_step_once() -> None:
    answer, llm = run_with([EXTRACT_OK, EXPLAIN_OK, OPTIONS_OK, REPLY_OK])
    assert len(llm.calls) == 4
    assert "Point: $1,284.50." in answer.explanation_en
    assert "If you disagree with this reassessment:" in answer.options_en
    assert answer.reply_en.startswith("Dear Northfield Revenue Office,")
    assert READER_NOT_SURE not in answer.text()


def test_answer_text_shows_english_then_farsi_and_the_disclaimer() -> None:
    answer, _ = run_with([EXTRACT_OK, EXPLAIN_OK, OPTIONS_OK, REPLY_OK])
    text = answer.text()
    assert text.index(answer.explanation_en) < text.index(answer.explanation_fa)
    assert text.rstrip().endswith(answer.disclaimer_fa)
    assert "General information only, not legal or tax advice." in text


def test_extract_failure_shows_only_not_sure_and_logs_the_error_type(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="letterbox")
    answer, llm = run_with([BAD, BAD])
    assert len(llm.calls) == 2
    assert answer.explanation_en == not_sure_line()
    assert answer.explanation_fa == not_sure_line(farsi=True)
    assert answer.options_en == answer.reply_en == ""
    assert "validation error" not in answer.text().lower()
    assert any("step=extract" in r.getMessage() and RUN_ID in r.getMessage() and "error=ValidationError" in r.getMessage()
               for r in caplog.records)


def test_no_verified_facts_goes_to_not_sure_without_more_calls(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="letterbox")
    made_up = json.dumps({"facts": [{"kind": "purpose", "value": "A notice.", "evidence": "This sentence is not there."}]})
    answer, llm = run_with([made_up])
    assert len(llm.calls) == 1
    assert answer.explanation_en == not_sure_line()
    assert any("verify" in r.getMessage() and RUN_ID in r.getMessage() for r in caplog.records)


def test_explain_failure_stops_before_options_and_reply() -> None:
    answer, llm = run_with([EXTRACT_OK, BAD, BAD])
    assert len(llm.calls) == 3
    assert answer.explanation_en == not_sure_line()
    assert answer.options_en == answer.reply_en == ""


def test_options_failure_shows_not_sure_for_options_only(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.WARNING, logger="letterbox")
    answer, llm = run_with([EXTRACT_OK, EXPLAIN_OK, BAD, BAD, REPLY_OK])
    assert len(llm.calls) == 5
    assert "Point: $1,284.50." in answer.explanation_en
    assert answer.options_en == not_sure_line()
    assert answer.options_fa == not_sure_line(farsi=True)
    assert answer.reply_en.startswith("Dear Northfield Revenue Office,")
    assert any("options" in r.getMessage() and RUN_ID in r.getMessage() for r in caplog.records)


def test_reply_failure_shows_not_sure_for_reply_only() -> None:
    answer, llm = run_with([EXTRACT_OK, EXPLAIN_OK, OPTIONS_OK, BAD, BAD])
    assert len(llm.calls) == 5
    assert answer.reply_en == not_sure_line()
    assert answer.reply_fa == not_sure_line(farsi=True)
    assert "If you disagree with this reassessment:" in answer.options_en


def test_each_run_gets_its_own_reference_by_default() -> None:
    first = run(LETTER, FakeLLM([BAD, BAD]))
    second = run(LETTER, FakeLLM([BAD, BAD]))
    assert first.explanation_en != second.explanation_en
    assert first.explanation_en.startswith(READER_NOT_SURE)


MODEL_MARKER = "MODEL-ANSWER-7f3a"
LETTER_LINES = [line.strip() for line in LETTER.splitlines() if line.strip()]
MODEL_TEXT_BAD = f"Sorry, {LETTER_LINES[6]} {MODEL_MARKER}"
SCHEMA_BAD = json.dumps({"facts": [{"kind": "amount", "value": f"$1,284.50 {MODEL_MARKER}"}]})
EXPLAIN_BAD = json.dumps(
    {"items": [{"fact": "F1", "english": f"Pay $1,284.50 now {MODEL_MARKER}", "farsi": "نکته"}]}
)
VERIFY_BAD = json.dumps(
    {"facts": [{"kind": "purpose", "value": f"{LETTER_LINES[6]} {MODEL_MARKER}", "evidence": f"Made up {MODEL_MARKER}."}]}
)
LOG_CASES = {
    "extract, model text": ([MODEL_TEXT_BAD, MODEL_TEXT_BAD], "step=extract", "error=ValidationError attempts=2"),
    "extract, schema": ([SCHEMA_BAD, SCHEMA_BAD], "step=extract", "error=ValidationError attempts=2"),
    "verify": ([VERIFY_BAD], "step=verify", "error=NoVerifiedFacts facts=1 dropped=1"),
    "explain": ([EXTRACT_OK, EXPLAIN_BAD, EXPLAIN_BAD], "step=explain", "error=ValueError attempts=2"),
    "options": ([EXTRACT_OK, EXPLAIN_OK, EXPLAIN_BAD, EXPLAIN_BAD, REPLY_OK], "step=options", "error=ValidationError attempts=2"),
    "reply": ([EXTRACT_OK, EXPLAIN_OK, OPTIONS_OK, MODEL_TEXT_BAD, MODEL_TEXT_BAD], "step=reply", "error=ValidationError attempts=2"),
}


@pytest.mark.parametrize("responses, step, details", LOG_CASES.values(), ids=LOG_CASES.keys())
def test_log_has_no_letter_or_model_text_only_step_error_reference_and_counts(
    caplog: pytest.LogCaptureFixture, responses: list[str], step: str, details: str
) -> None:
    caplog.set_level(logging.DEBUG)
    run_with(responses)
    log = "\n".join(record.getMessage() for record in caplog.records)
    assert MODEL_MARKER not in log
    for fragment in [*LETTER_LINES, "$1,284.50", "TEST-REF-001"]:
        assert fragment not in log, f"letter text in log: {fragment!r}"
    assert f"run {RUN_ID}: {step} not sure: {details}" in log
