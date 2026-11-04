"""Logging configuration shared by the CLI and scripts."""

import logging

from ai_avatar.redact import scrub


class _ScrubFilter(logging.Filter):
    """Redact secrets from every record (urllib3 logs full URLs, including ``?key=...``, at DEBUG)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg, record.args = scrub(record.getMessage()), None
        return True


def setup_logging(verbosity: int = 0) -> None:
    """``-1`` quiet (warnings), ``0`` info, ``1+`` debug."""
    level = logging.WARNING if verbosity < 0 else logging.DEBUG if verbosity > 0 else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    for handler in logging.getLogger().handlers:
        if not any(isinstance(f, _ScrubFilter) for f in handler.filters):
            handler.addFilter(_ScrubFilter())
