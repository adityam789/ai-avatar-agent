"""Research cache: TTL, expiry, persistence, corrupt files."""

import json
import os
from pathlib import Path

import pytest

from ai_avatar.research.cache import DiskResearchCache, ResearchCache
from ai_avatar.research.schemas import ResearchBundle

HOUR = 3600
DAY0 = 1_700_000_000.0  # fixed instant: 2023-11-14 22:13 UTC


class Clock:
    def __init__(self, now=DAY0):
        self.now = now

    def __call__(self):
        return self.now


def bundle(topic="Black Holes"):
    return ResearchBundle(topic, ["f1", "f2"], "fresh", ["rss"], [{"source": "rss", "title": "t", "url": "http://u"}])


@pytest.fixture(params=["memory", "disk"])
def make_cache(request, tmp_path):
    def make(ttl_hours=24.0, clock=None):
        clock = clock or Clock()
        if request.param == "memory":
            return ResearchCache(ttl_hours, clock)
        return DiskResearchCache(tmp_path / "cache", ttl_hours, clock)

    return make


def test_miss_then_hit_marks_bundle_cached(make_cache):
    cache = make_cache()
    assert cache.find("Black Holes") is None
    cache.store(bundle())
    hit = cache.find("Black Holes")
    assert hit.freshness == "cached"
    assert (hit.facts, hit.sources, hit.source_links) == (["f1", "f2"], ["rss"], bundle().source_links)


def test_entry_is_served_just_before_ttl_and_never_after(make_cache):
    clock = Clock()
    cache = make_cache(ttl_hours=1, clock=clock)  # DAY0 is 22:13 UTC, so +1h stays on the same date
    cache.store(bundle())
    clock.now = DAY0 + HOUR - 1
    assert cache.find("Black Holes") is not None
    clock.now = DAY0 + HOUR
    assert cache.find("Black Holes") is None
    clock.now = DAY0 + HOUR + 1
    assert cache.find("Black Holes") is None


def test_clock_moved_backwards_is_a_miss_not_a_hit(make_cache):
    clock = Clock()
    cache = make_cache(clock=clock)
    cache.store(bundle())
    clock.now = DAY0 - 60  # same UTC date, but "before" the entry was stored
    assert cache.find("Black Holes") is None


def test_zero_ttl_disables_the_cache(make_cache):
    cache = make_cache(ttl_hours=0)
    cache.store(bundle())
    assert cache.find("Black Holes") is None


def test_topics_are_independent(make_cache):
    cache = make_cache()
    cache.store(bundle("Black Holes"))
    assert cache.find("Neutron stars") is None


def test_disk_cache_survives_a_new_instance_and_uses_slug_and_date(tmp_path):
    clock = Clock()
    DiskResearchCache(tmp_path, 24, clock).store(bundle())
    assert [p.name for p in tmp_path.iterdir()] == ["2023-11-14_black-holes.json"]
    assert DiskResearchCache(tmp_path, 24, clock).find("Black Holes").facts == ["f1", "f2"]


def test_disk_cache_with_long_ttl_still_misses_on_the_next_day(tmp_path):
    clock = Clock()
    cache = DiskResearchCache(tmp_path, ttl_hours=1000, clock=clock)
    cache.store(bundle())
    clock.now = DAY0 + 24 * HOUR  # next UTC date: different key
    assert cache.find("Black Holes") is None


def test_disk_cache_checks_stored_time_not_just_the_file_name(tmp_path):
    cache = DiskResearchCache(tmp_path, ttl_hours=1, clock=Clock())
    cache.store(bundle())
    path = next(tmp_path.iterdir())
    record = json.loads(path.read_text())
    record["stored_at"] = DAY0 - 3 * HOUR  # file name still carries today's date
    path.write_text(json.dumps(record))
    assert cache.find("Black Holes") is None


@pytest.mark.parametrize("content", ["not json", "[]", '{"stored_at": 1}', '{"stored_at": "x", "bundle": {}}'])
def test_disk_cache_treats_corrupt_files_as_a_miss(tmp_path, content):
    cache = DiskResearchCache(tmp_path, 24, Clock())
    cache.store(bundle())
    next(tmp_path.iterdir()).write_text(content)
    assert cache.find("Black Holes") is None


def test_disk_cache_rejects_a_file_for_a_different_topic_with_same_slug(tmp_path):
    cache = DiskResearchCache(tmp_path, 24, Clock())
    cache.store(bundle("Black Holes"))
    assert cache.find("black holes!") is None  # same slug, different topic text


def test_failed_write_leaves_the_previous_cache_file_intact(tmp_path, monkeypatch, caplog):
    cache = DiskResearchCache(tmp_path, 24, Clock())
    cache.store(bundle())
    path = next(tmp_path.iterdir())
    before = path.read_text()

    def failing_replace(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", failing_replace)
    cache.store(ResearchBundle("Black Holes", ["new fact"], "fresh", ["rss"]))
    assert path.read_text() == before  # the old file was never truncated
    assert list(tmp_path.iterdir()) == [path]  # and no temp file is left behind
    assert "could not write research cache file" in caplog.text


def test_store_writes_through_a_temp_file_in_the_same_directory(tmp_path, monkeypatch):
    moves = []
    real_replace = os.replace
    monkeypatch.setattr(os, "replace", lambda src, dst: (moves.append((Path(src), Path(dst))), real_replace(src, dst)))
    DiskResearchCache(tmp_path, 24, Clock()).store(bundle())
    (src, dst), = moves
    assert src.parent == dst.parent == tmp_path and src != dst and src.suffix == ".tmp"
    assert [p.name for p in tmp_path.iterdir()] == [dst.name]


def test_disk_cache_leaves_no_temp_file_when_serialising_fails(tmp_path):
    cache = DiskResearchCache(tmp_path / "c", ttl_hours=24, clock=Clock())
    bad = bundle()
    bad.source_links.append({"source": "rss", "title": object(), "url": "u"})  # json.dump raises TypeError
    with pytest.raises(TypeError):
        cache.store(bad)
    assert list((tmp_path / "c").glob("*")) == []
