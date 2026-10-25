"""Logging for the command line and the eval."""

import logging

# The SDK's own debug logs can include the request, and so the letter.
SDK_LOGGERS = ("anthropic", "httpx2")


def configure_logging() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    quiet_sdk_loggers()


def quiet_sdk_loggers() -> None:
    """Keep SDK loggers at warning, even if ANTHROPIC_LOG=debug was set."""
    for name in SDK_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
