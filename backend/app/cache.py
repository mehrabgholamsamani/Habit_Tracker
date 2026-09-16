"""Small, defensive Redis cache-aside primitives.

Keys are versioned and user-scoped.  Cached values are JSON only: accepting
pickle (or arbitrary Python objects) would turn a compromised Redis instance
into a code-execution path.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from typing import TypeAlias

from redis import Redis
from redis.exceptions import RedisError

from .redis_client import redis_client
from .logging_config import log_dependency_warning
from .metrics import record_cache


logger = logging.getLogger(__name__)

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]

_SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PREFIX = "habit-cache"
_VERSION = "v1"
_MAX_KEY_BYTES = 256
_MAX_VALUE_BYTES = 512 * 1024
_MAX_TTL_SECONDS = 7 * 24 * 60 * 60
_CONDITIONAL_SET_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if (current == false and ARGV[1] == '0') or current == ARGV[1] then
    redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3])
    return 1
end
return 0
"""


def _positive_env(name: str, default: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not 1 <= value <= maximum:
        raise RuntimeError(f"{name} must be between 1 and {maximum}")
    return value


@dataclass(frozen=True)
class CacheTTLs:
    """Cache lifetimes, overridable without changing endpoint contracts."""

    default: int
    habits: int
    users: int

    @classmethod
    def from_env(cls) -> "CacheTTLs":
        return cls(
            default=_positive_env("CACHE_TTL_SECONDS", 60, _MAX_TTL_SECONDS),
            habits=_positive_env("CACHE_HABITS_TTL_SECONDS", 60, _MAX_TTL_SECONDS),
            users=_positive_env("CACHE_USERS_TTL_SECONDS", 300, _MAX_TTL_SECONDS),
        )


cache_ttls = CacheTTLs.from_env()


def _segment(value: str | int, label: str) -> str:
    rendered = str(value)
    if not _SEGMENT.fullmatch(rendered):
        raise ValueError(f"invalid cache key {label}")
    return rendered


def cache_key(
    namespace: str,
    *,
    user_id: int | None = None,
    generation: int = 0,
    resource_id: str | int | None = None,
) -> str:
    """Build a deterministic, bounded key with optional user isolation."""

    parts = [_PREFIX, _VERSION, _segment(namespace, "namespace")]
    if user_id is not None:
        if user_id <= 0 or generation < 0:
            raise ValueError("user_id must be positive and generation non-negative")
        parts.extend(("u", str(user_id), "g", str(generation)))
    elif generation:
        raise ValueError("generation requires user_id")
    if resource_id is not None:
        parts.extend(("r", _segment(resource_id, "resource_id")))
    key = ":".join(parts)
    if len(key.encode("utf-8")) > _MAX_KEY_BYTES:
        raise ValueError("cache key is too long")
    return key


class Cache:
    """Bounded JSON cache which treats Redis outages as cache misses."""

    def __init__(self, client: Redis):
        self._client = client

    def get_json(self, key: str) -> JSONValue | None:
        try:
            raw = self._client.get(key)
            if raw is None:
                record_cache("get", "miss")
                logger.debug("Cache miss", extra={"event": "cache_miss", "cache_result": "miss"})
                return None
            if len(raw.encode("utf-8")) > _MAX_VALUE_BYTES:
                self._safe_delete(key)
                record_cache("get", "rejected")
                return None
            try:
                value = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                self._safe_delete(key)
                record_cache("get", "rejected")
                return None
            if not _is_json_value(value):
                self._safe_delete(key)
                record_cache("get", "rejected")
                return None
            record_cache("get", "hit")
            logger.debug("Cache hit", extra={"event": "cache_hit", "cache_result": "hit"})
            return value
        except (RedisError, UnicodeError):
            record_cache("get", "error")
            log_dependency_warning(logger, "cache_read_error", dependency="redis", operation="get")
            return None

    def set_json(
        self, key: str, value: JSONValue, ttl_seconds: int | None = None
    ) -> bool:
        if ttl_seconds is None:
            ttl_seconds = cache_ttls.default
        if not 1 <= ttl_seconds <= _MAX_TTL_SECONDS:
            raise ValueError("cache TTL is outside the allowed range")
        payload = self._encode(value)
        if payload is None:
            record_cache("set", "rejected")
            return False
        try:
            result = bool(self._client.set(key, payload, ex=ttl_seconds))
            record_cache("set", "success" if result else "error")
            return result
        except RedisError:
            record_cache("set", "error")
            log_dependency_warning(logger, "cache_write_error", dependency="redis", operation="set")
            return False

    def set_json_if_generation(
        self,
        key: str,
        value: JSONValue,
        *,
        generation: int,
        user_id: int | None = None,
        namespace: str | None = None,
        ttl_seconds: int | None = None,
    ) -> bool:
        """Set only if no invalidation occurred while data was being loaded."""
        ttl = ttl_seconds or cache_ttls.default
        if not 1 <= ttl <= _MAX_TTL_SECONDS or generation < 0:
            raise ValueError("cache TTL or generation is outside the allowed range")
        if (user_id is None) == (namespace is None):
            raise ValueError("provide exactly one generation scope")
        payload = self._encode(value)
        if payload is None:
            record_cache("set", "rejected")
            return False
        generation_key = (
            self._generation_key(user_id)
            if user_id is not None
            else self._global_generation_key(namespace or "")
        )
        try:
            result = bool(
                self._client.eval(
                    _CONDITIONAL_SET_SCRIPT,
                    2,
                    generation_key,
                    key,
                    generation,
                    payload,
                    ttl,
                )
            )
            record_cache("set", "success" if result else "rejected")
            return result
        except RedisError:
            record_cache("set", "error")
            log_dependency_warning(logger, "cache_conditional_write_error", dependency="redis", operation="conditional_set")
            return False

    def delete_keys(self, *keys: str) -> bool:
        if not keys:
            return True
        try:
            self._client.delete(*keys)
            record_cache("delete", "success")
            logger.info("Cache invalidated", extra={"event": "cache_invalidation", "operation": "delete", "outcome": "success"})
            return True
        except RedisError:
            record_cache("delete", "error")
            log_dependency_warning(logger, "cache_invalidation_error", dependency="redis", operation="delete")
            return False

    def user_cache_key(
        self, namespace: str, user_id: int, resource_id: str | int | None = None
    ) -> str:
        generation = 0
        try:
            raw = self._client.get(self._generation_key(user_id))
            if raw is not None:
                generation = max(0, int(raw))
        except (RedisError, TypeError, ValueError):
            log_dependency_warning(logger, "cache_generation_read_error", dependency="redis", operation="generation_get")
        return cache_key(
            namespace, user_id=user_id, generation=generation, resource_id=resource_id
        )

    def user_cache_key_with_generation(
        self, namespace: str, user_id: int, resource_id: str | int | None = None
    ) -> tuple[str, int]:
        generation = self._read_generation(self._generation_key(user_id))
        return (
            cache_key(
                namespace,
                user_id=user_id,
                generation=generation,
                resource_id=resource_id,
            ),
            generation,
        )

    def global_cache_key_with_generation(self, namespace: str) -> tuple[str, int]:
        generation = self._read_generation(self._global_generation_key(namespace))
        return cache_key(namespace, resource_id=f"g-{generation}"), generation

    def invalidate_global_cache(self, namespace: str) -> bool:
        return self._increment_generation(self._global_generation_key(namespace))

    def invalidate_user_cache(self, user_id: int) -> bool:
        """Invalidate all user data in O(1), avoiding Redis key scans."""

        return self._increment_generation(self._generation_key(user_id))

    def _increment_generation(self, key: str) -> bool:
        try:
            pipeline = self._client.pipeline(transaction=True)
            pipeline.incr(key)
            pipeline.expire(key, _MAX_TTL_SECONDS)
            pipeline.execute()
            record_cache("invalidate", "success")
            logger.info("Cache invalidated", extra={"event": "cache_invalidation", "operation": "generation_increment", "outcome": "success"})
            return True
        except RedisError:
            record_cache("invalidate", "error")
            log_dependency_warning(logger, "cache_invalidation_error", dependency="redis", operation="generation_increment")
            return False

    def _read_generation(self, key: str) -> int:
        try:
            raw = self._client.get(key)
            return max(0, int(raw)) if raw is not None else 0
        except (RedisError, TypeError, ValueError):
            log_dependency_warning(logger, "cache_generation_read_error", dependency="redis", operation="generation_get")
            return 0

    def _generation_key(self, user_id: int) -> str:
        if user_id <= 0:
            raise ValueError("user_id must be positive")
        return f"{_PREFIX}:{_VERSION}:generation:u:{user_id}"

    def _global_generation_key(self, namespace: str) -> str:
        return f"{_PREFIX}:{_VERSION}:generation:global:{_segment(namespace, 'namespace')}"

    def _encode(self, value: JSONValue) -> str | None:
        try:
            payload = json.dumps(
                value, ensure_ascii=False, allow_nan=False, separators=(",", ":"), sort_keys=True
            )
        except (TypeError, ValueError):
            return None
        return payload if len(payload.encode("utf-8")) <= _MAX_VALUE_BYTES else None

    def _safe_delete(self, key: str) -> None:
        try:
            self._client.delete(key)
        except RedisError:
            pass


def _is_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return value == value and value not in (float("inf"), float("-inf"))
    if isinstance(value, list):
        return all(_is_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, str) and _is_json_value(item) for key, item in value.items())
    return False


cache = Cache(redis_client)
