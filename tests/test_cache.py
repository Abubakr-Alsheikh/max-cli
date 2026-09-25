from pathlib import Path
from types import SimpleNamespace

import pytest

from max_cli.common import cache as cache_module
from max_cli.common.cache import Cache, cached, get_default_cache

START_TIME = 1_000_000.0


class FakeClock:
    """Stands in for time.time inside max_cli.common.cache."""

    def __init__(self, now: float = START_TIME) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> FakeClock:
    fake_clock = FakeClock()
    # Swap the module's `time` reference so the global time.time stays real.
    monkeypatch.setattr(cache_module, "time", SimpleNamespace(time=fake_clock))
    return fake_clock


@pytest.fixture
def cache_dir(tmp_path) -> Path:
    return tmp_path / "cache"


@pytest.fixture
def cache(cache_dir, clock) -> Cache:
    return Cache(cache_dir=cache_dir, ttl=60)


@pytest.fixture
def default_cache(monkeypatch, cache_dir, clock) -> Cache:
    """Point get_default_cache() and @cached at a tmp_path cache."""
    test_cache = Cache(cache_dir=cache_dir, ttl=60)
    monkeypatch.setattr(cache_module, "_default_cache", test_cache)
    return test_cache


def test_init_creates_cache_dir(cache_dir, clock):
    Cache(cache_dir=cache_dir)

    assert cache_dir.is_dir()


def test_default_dir_lives_under_home(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: fake_home)

    assert Cache().cache_dir == fake_home / ".max_cli" / "cache"
    assert (fake_home / ".max_cli" / "cache").is_dir()


def test_set_then_get_round_trips_json_values(cache):
    cache.set("key", {"list": [1, 2], "text": "é"})

    assert cache.get("key") == {"list": [1, 2], "text": "é"}


def test_get_missing_key_returns_none(cache):
    assert cache.get("nope") is None


def test_entry_expires_after_ttl(cache, clock):
    cache.set("key", "value")

    clock.advance(59)
    assert cache.get("key") == "value"

    clock.advance(2)
    assert cache.get("key") is None
    assert cache.count() == 0


def test_per_entry_ttl_overrides_default(cache, clock):
    cache.set("short", "a", ttl=5)
    cache.set("long", "b", ttl=500)

    clock.advance(10)

    assert cache.get("short") is None
    assert cache.get("long") == "b"


def test_zero_ttl_override_is_respected(cache, clock):
    cache.set("key", "value", ttl=0)

    clock.advance(1)

    assert cache.get("key") is None


def test_corrupt_entry_reads_as_none(cache, cache_dir):
    cache.set("key", "value")
    (cache_file,) = cache_dir.glob("*.json")
    cache_file.write_text("{not json", encoding="utf-8")

    assert cache.get("key") is None


def test_delete(cache):
    cache.set("key", "value")

    assert cache.delete("key") is True
    assert cache.get("key") is None
    assert cache.delete("key") is False


def test_count_size_and_clear(cache):
    assert cache.count() == 0
    assert cache.get_size() == 0

    cache.set("a", "x" * 100)
    cache.set("b", "y")

    assert cache.count() == 2
    assert cache.get_size() > 100

    assert cache.clear() == 2
    assert cache.count() == 0
    assert cache.get_size() == 0


def test_clear_expired_keeps_fresh_and_drops_stale_and_corrupt(cache, cache_dir, clock):
    cache.set("stale", 1, ttl=5)
    cache.set("fresh", 2, ttl=500)
    (cache_dir / "broken.json").write_text("{", encoding="utf-8")

    clock.advance(10)

    assert cache.clear_expired() == 2
    assert cache.count() == 1
    assert cache.get("fresh") == 2


def test_get_default_cache_is_a_singleton(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(cache_module, "_default_cache", None)

    first = get_default_cache()

    assert get_default_cache() is first
    assert first.cache_dir == tmp_path / "home" / ".max_cli" / "cache"


def test_cached_decorator_reuses_result(default_cache):
    calls = []

    @cached("square")
    def square(number: int) -> int:
        calls.append(number)
        return number * number

    assert square(4) == 16
    assert square(4) == 16
    assert square(5) == 25
    assert calls == [4, 5]


def test_cached_decorator_keys_on_kwargs(default_cache):
    calls = []

    @cached("greet")
    def greet(name: str = "x") -> str:
        calls.append(name)
        return f"hi {name}"

    greet(name="a")
    greet(name="a")
    greet(name="b")

    assert calls == ["a", "b"]


def test_cached_decorator_honours_ttl(default_cache, clock):
    calls = []

    @cached("stamp", ttl=10)
    def stamp() -> int:
        calls.append(1)
        return len(calls)

    assert stamp() == 1
    clock.advance(5)
    assert stamp() == 1
    clock.advance(10)
    assert stamp() == 2


def test_cached_decorator_does_not_cache_none(default_cache):
    calls = []

    @cached("nothing")
    def nothing() -> None:
        calls.append(1)

    nothing()
    nothing()

    assert len(calls) == 2


@pytest.mark.xfail(
    strict=True,
    reason="@cached drops Path arguments from the key, so calls with different "
    "paths share one cache entry and return stale results",
)
def test_cached_decorator_distinguishes_path_arguments(default_cache, tmp_path):
    @cached("name")
    def file_name(path: Path) -> str:
        return path.name

    assert file_name(tmp_path / "a.txt") == "a.txt"
    assert file_name(tmp_path / "b.txt") == "b.txt"
