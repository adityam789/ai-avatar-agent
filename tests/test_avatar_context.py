"""The SadTalker context manager must restore sys.path/argv even when SadTalker raises."""

import importlib.util
import sys

import pytest

from ai_avatar.config import load_config
from ai_avatar.stages.avatar import _sadtalker_context


def test_context_puts_sadtalker_first_and_restores_on_error():
    cfg = load_config(environ={})
    path_before, argv0_before = list(sys.path), sys.argv[0]
    with pytest.raises(RuntimeError):
        with _sadtalker_context(cfg):
            assert sys.path[0] == str(cfg.sadtalker_dir)
            assert sys.path[1] == str(cfg.root)
            assert sys.argv[0].startswith(str(cfg.root))
            raise RuntimeError("boom")
    assert sys.path == path_before
    assert sys.argv[0] == argv0_before


def test_sadtalker_src_wins_over_repo_src():
    cfg = load_config(environ={})
    if not (cfg.sadtalker_dir / "src" / "utils").is_dir():
        pytest.skip("SadTalker submodule not checked out")
    with _sadtalker_context(cfg):
        spec = importlib.util.find_spec("src.utils.preprocess")
    assert spec and str(cfg.sadtalker_dir) in spec.origin
