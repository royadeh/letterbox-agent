"""Text matching that ignores differences in spaces and line breaks."""

import re


def normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def appears_in(part: str, whole: str) -> bool:
    """True if `part` is in `whole` word for word, ignoring spacing and line breaks."""
    return normalize_whitespace(part) in normalize_whitespace(whole)
