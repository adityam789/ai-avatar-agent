"""Smoke tests: the package imports without any heavy extras installed."""

import ai_avatar


def test_version():
    assert ai_avatar.__version__
