import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional


class Cache:
    """Simple file-based cache with TTL support."""

    def __init__(self, cache_dir: Optional[Path] = None, ttl: int = 3600):
        """Initialize cache.

        Args:
            cache_dir: Directory for cache files. Defaults to ~/.max_cli/cache
            ttl: Time-to-live in seconds for cached items. Default 1 hour.
        """
        self.cache_dir = cache_dir or Path.home() / ".max_cli" / "cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl = ttl

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        cache_file = self.cache_dir / f"{self._hash(key)}.json"
        if not cache_file.exists():
            return None

        try:
            data = json.loads(cache_file.read_text())
            if data.get("expires", 0) < time.time():
                cache_file.unlink()
                return None
            return data.get("value")
        except (json.JSONDecodeError, OSError):
            return None

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Optional TTL override in seconds
        """
        cache_file = self.cache_dir / f"{self._hash(key)}.json"
        expires = time.time() + (ttl if ttl is not None else self.ttl)
        data = {"value": value, "expires": expires}
        cache_file.write_text(json.dumps(data))

    def delete(self, key: str) -> bool:
        """Delete a cached item.

        Args:
            key: Cache key

        Returns:
            True if deleted, False if not found
        """
        cache_file = self.cache_dir / f"{self._hash(key)}.json"
        if cache_file.exists():
            cache_file.unlink()
            return True
        return False

    def clear(self) -> int:
        """Clear all cache entries.

        Returns:
            Number of entries cleared
        """
        count = 0
        for f in self.cache_dir.glob("*.json"):
            f.unlink()
            count += 1
        return count

    def clear_expired(self) -> int:
        """Clear only expired cache entries.

        Returns:
            Number of expired entries cleared
        """
        count = 0
        now = time.time()
        for f in self.cache_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("expires", 0) < now:
                    f.unlink()
                    count += 1
            except (json.JSONDecodeError, OSError):
                f.unlink()
                count += 1
        return count

    def _hash(self, key: str) -> str:
        """Generate hash for cache key."""
        return hashlib.md5(key.encode()).hexdigest()


_default_cache: Optional[Cache] = None


def get_default_cache() -> Cache:
    """Get the default cache instance."""
    global _default_cache
    if _default_cache is None:
        _default_cache = Cache()
    return _default_cache


def cached(key_prefix: str, ttl: Optional[int] = None):
    """Decorator for caching function results.

    Args:
        key_prefix: Prefix for cache key
        ttl: Optional TTL override in seconds
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            cache = get_default_cache()
            key_parts = [key_prefix]
            key_parts.extend(str(arg) for arg in args if not isinstance(arg, Path))
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = ":".join(key_parts)

            result = cache.get(cache_key)
            if result is not None:
                return result

            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result

        return wrapper

    return decorator
