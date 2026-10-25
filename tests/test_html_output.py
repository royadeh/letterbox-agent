import re

from letterbox.graph import DISCLAIMER, DISCLAIMER_FA, Answer
from letterbox.html_output import render_html

ANSWER = Answer(
    explanation_en="Pay <b>now</b> & then.\nSecond line.",
    explanation_fa="<script>alert(1)</script> نکته",
    reply_en="Dear Office,",
    reply_fa="این پیش‌نویس",
    reply_note_en="Sending this reply may not change any deadline in the letter.",
    reply_note_fa="یادداشت",
)


def sections(html: str) -> list[str]:
    return re.findall(r"<section[^>]*>", html)


def test_html_is_a_complete_utf8_page() -> None:
    html = render_html(ANSWER)
    assert html.startswith("<!DOCTYPE html>")
    assert '<meta charset="utf-8">' in html
    assert html.rstrip().endswith("</html>")


def test_all_text_is_escaped() -> None:
    html = render_html(ANSWER)
    assert "<b>now</b>" not in html and "<script>" not in html
    assert "Pay &lt;b&gt;now&lt;/b&gt; &amp; then." in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_farsi_sections_are_right_to_left_and_english_are_not() -> None:
    tags = sections(render_html(ANSWER))
    assert tags == [
        '<section lang="en">',
        '<section lang="fa" dir="rtl">',
        '<section lang="en">',
        '<section lang="fa" dir="rtl">',
    ]


def test_empty_sections_are_left_out() -> None:
    assert "Your options" not in render_html(ANSWER)


def test_reply_note_is_shown_before_the_draft() -> None:
    html = render_html(ANSWER)
    assert html.index("Sending this reply may not change") < html.index("Dear Office,")
    assert html.index("یادداشت") < html.index("این پیش‌نویس")


def test_disclaimer_is_kept_in_both_languages() -> None:
    html = render_html(ANSWER)
    assert DISCLAIMER in html
    assert f'<p lang="fa" dir="rtl">{DISCLAIMER_FA}</p>' in html
