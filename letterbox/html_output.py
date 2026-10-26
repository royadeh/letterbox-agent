"""A simple HTML page with the English and Farsi answer. All text is escaped.

Values copied from the letter are marked in the Farsi text with Unicode
isolates; on the page they become <bdi dir="ltr">, so punctuation after an
English value inside a Farsi sentence lands in the right place.
"""

import re
from html import escape

from letterbox.graph import Answer, Section
from letterbox.placeholders import FIRST_STRONG_ISOLATE, POP_DIRECTIONAL_ISOLATE

ISOLATED = re.compile(f"{FIRST_STRONG_ISOLATE}(.*?){POP_DIRECTIONAL_ISOLATE}", re.DOTALL)

STYLE = (
    "body { font-family: sans-serif; max-width: 42em; margin: 2em auto; padding: 0 1em; line-height: 1.6; }"
    " .body { white-space: pre-wrap; }"
    " .note { font-style: italic; }"
    " footer { margin-top: 2em; border-top: 1px solid #ccc; }"
)


def render_html(answer: Answer) -> str:
    sections = "\n".join(_section(section) for section in answer.sections())
    return (
        "<!DOCTYPE html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        "<title>Letterbox</title>\n"
        f"<style>{STYLE}</style>\n"
        "</head>\n"
        "<body>\n"
        f"{sections}\n"
        "<footer>\n"
        f'<p lang="en">{escape(answer.disclaimer_en)}</p>\n'
        f'<p lang="fa" dir="rtl">{escape(answer.disclaimer_fa)}</p>\n'
        "</footer>\n"
        "</body>\n"
        "</html>\n"
    )


def _section(section: Section) -> str:
    language = ' lang="fa" dir="rtl"' if section.farsi else ' lang="en"'
    note = f'<p class="note">{escape(section.note)}</p>\n' if section.note else ""
    return (
        f"<section{language}>\n"
        f"<h2>{escape(section.title)}</h2>\n"
        f"{note}"
        f'<div class="body">{_body(section.body)}</div>\n'
        "</section>"
    )


def _body(text: str) -> str:
    """Escape everything; wrap each copied value in <bdi dir="ltr">."""
    parts: list[str] = []
    position = 0
    for match in ISOLATED.finditer(text):
        parts.append(_escape_plain(text[position : match.start()]))
        parts.append(f'<bdi dir="ltr">{_escape_plain(match.group(1))}</bdi>')
        position = match.end()
    parts.append(_escape_plain(text[position:]))
    return "".join(parts)


def _escape_plain(text: str) -> str:
    stray = {FIRST_STRONG_ISOLATE: "", POP_DIRECTIONAL_ISOLATE: ""}
    return escape(text.translate(str.maketrans(stray)))
