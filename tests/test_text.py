from letterbox.text import appears_in, normalize_whitespace


def test_normalize_whitespace_collapses_spaces_and_line_breaks() -> None:
    assert normalize_whitespace("  The fine\nis   $65.00.\t ") == "The fine is $65.00."


def test_appears_in_ignores_spaces_and_line_breaks() -> None:
    assert appears_in("The fine for this violation is $65.00.", "The fine for\nthis violation is  $65.00.")


def test_appears_in_still_needs_the_same_words_and_numbers() -> None:
    assert not appears_in("The fine is $56.00.", "The fine is $65.00.")
    assert not appears_in("The penalty is $65.00.", "The fine is $65.00.")
