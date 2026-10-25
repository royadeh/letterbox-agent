import html
import logging
from collections.abc import Iterator
from pathlib import Path

import anthropic
import pytest
from anthropic._utils._logs import setup_logging

from conftest import LETTERS_DIR, FakeLLM
from letterbox.__main__ import main
from letterbox.graph import READER_NOT_SURE

LETTER_PATH = LETTERS_DIR / "001_tax_reassessment.txt"


def test_cli_reads_the_letter_file_and_prints_the_answer(capsys: pytest.CaptureFixture[str]) -> None:
    llm = FakeLLM(["not json", "not json"])
    exit_code = main([str(LETTER_PATH)], client_factory=lambda: llm)
    out = capsys.readouterr().out
    assert exit_code == 0
    assert READER_NOT_SURE in out
    assert "validation error" not in out.lower()
    assert "Northfield Revenue Office" in llm.calls[0].user


def test_cli_with_a_missing_file_prints_a_short_error(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    llm = FakeLLM([])
    exit_code = main([str(tmp_path / "missing.txt")], client_factory=lambda: llm)
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Could not read the letter file." in captured.err
    assert "Traceback" not in captured.err
    assert llm.calls == []


def test_cli_without_an_api_key_prints_a_short_error(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = main([str(LETTER_PATH)])
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "ANTHROPIC_API_KEY" in captured.err


class FakeAPIError(anthropic.APIError):
    def __init__(self) -> None:
        Exception.__init__(self, "connection reset by peer")


def test_cli_model_call_error_prints_a_generic_message_with_a_reference(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="letterbox")
    exit_code = main([str(LETTER_PATH)], client_factory=lambda: FakeLLM([FakeAPIError()]))
    captured = capsys.readouterr()
    assert exit_code == 1
    assert "Something went wrong. (Reference: " in captured.err
    assert "connection reset" not in captured.err + captured.out
    log = "\n".join(record.getMessage() for record in caplog.records)
    assert "connection reset" not in log
    assert "step=model_call error=FakeAPIError" in log


SDK_LOGGERS = ("anthropic", "httpx2")


@pytest.fixture
def sdk_logger_levels() -> Iterator[None]:
    saved = {name: logging.getLogger(name).level for name in SDK_LOGGERS}
    yield
    for name, level in saved.items():
        logging.getLogger(name).setLevel(level)


@pytest.mark.usefixtures("sdk_logger_levels")
def test_cli_keeps_sdk_loggers_at_warning_even_with_anthropic_log_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_LOG", "debug")
    setup_logging()  # what the SDK does when it is imported
    assert logging.getLogger("anthropic").isEnabledFor(logging.DEBUG)
    main([str(LETTER_PATH)], client_factory=lambda: FakeLLM(["not json", "not json"]))
    for name in SDK_LOGGERS:
        assert not logging.getLogger(name).isEnabledFor(logging.INFO), name
        assert logging.getLogger(name).isEnabledFor(logging.WARNING), name


def test_cli_html_option_writes_the_answer_as_html(tmp_path: Path) -> None:
    output = tmp_path / "out.html"
    exit_code = main([str(LETTER_PATH), "--html", str(output)], client_factory=lambda: FakeLLM(["not json", "not json"]))
    assert exit_code == 0
    page = output.read_text(encoding="utf-8")
    assert html.escape(READER_NOT_SURE) in page
    assert 'dir="rtl"' in page
    assert "General information only, not legal or tax advice." in page


def test_cli_html_option_that_cannot_be_written_prints_a_short_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "missing-folder" / "out.html"
    exit_code = main([str(LETTER_PATH), "--html", str(output)], client_factory=lambda: FakeLLM(["not json", "not json"]))
    assert exit_code == 1
    assert "Could not write the HTML file." in capsys.readouterr().err
    assert not output.exists()
