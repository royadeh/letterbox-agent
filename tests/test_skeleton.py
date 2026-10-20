import letterbox


def test_package_imports_and_has_version() -> None:
    assert isinstance(letterbox.__version__, str)
