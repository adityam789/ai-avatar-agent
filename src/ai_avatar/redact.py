"""Scrub secrets from text before it is logged, stored in ``run.json`` or shown to the user.

Exception messages from ``requests`` include the full URL, and the Google CSE collector puts
its API key in the query string, so anything derived from an exception goes through :func:`scrub`.
"""

import os
import re

from ai_avatar.checks import ENV_VARS

_URL_SECRET = re.compile(r"(?i)([?&](?:key|api_key|apikey|token|access_token|client_secret)=)[^&\s'\")]+")
_MIN_SECRET_LEN = 6  # don't blank out trivially short values like "1"


def scrub(text: object) -> str:
    """``str(text)`` with secret env-var values and URL credentials replaced by ``***``."""
    out = _URL_SECRET.sub(r"\1***", str(text))
    for name, (_purpose, _required, secret) in ENV_VARS.items():
        value = os.getenv(name, "") if secret else ""
        if len(value) >= _MIN_SECRET_LEN:
            out = out.replace(value, "***")
    return out
