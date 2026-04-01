"""tools/cache.py 테스트."""

import json
import time

import pytest

from tools.cache import _cache_path, _read_cache, _write_cache, cached_api_call


class TestFileCache:
    def test_write_and_read_cache(self, tmp_path):
        path = tmp_path / "test.json"
        _write_cache(path, {"key": "value"})

        result = _read_cache(path, ttl_hours=1.0)
        assert result == {"key": "value"}

    def test_expired_cache_returns_none(self, tmp_path):
        path = tmp_path / "test.json"
        with open(path, "w") as f:
            json.dump({"timestamp": time.time() - 7200, "data": {"old": True}}, f)

        result = _read_cache(path, ttl_hours=1.0)
        assert result is None

    def test_corrupted_cache_returns_none(self, tmp_path):
        path = tmp_path / "test.json"
        with open(path, "w") as f:
            f.write("not json")

        result = _read_cache(path, ttl_hours=1.0)
        assert result is None


class TestCachedApiCall:
    def test_fetcher_called_on_miss(self):
        called = []
        def fetcher():
            called.append(True)
            return {"data": 42}

        result = cached_api_call("test:unique_key_1", fetcher, ttl_hours=0.001)
        assert result == {"data": 42}
        assert len(called) == 1

    def test_fetcher_failure_returns_none(self):
        def bad_fetcher():
            raise ConnectionError("network down")

        result = cached_api_call("test:unique_key_2", bad_fetcher, ttl_hours=1.0)
        assert result is None
