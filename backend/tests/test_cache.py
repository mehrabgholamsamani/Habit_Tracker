import json

import pytest
from redis.exceptions import RedisError

from app.cache import Cache, CacheTTLs, cache_key


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.commands = []

    def incr(self, key):
        self.commands.append(("incr", key))
        return self

    def expire(self, key, seconds):
        self.commands.append(("expire", key, seconds))
        return self

    def execute(self):
        for command in self.commands:
            if command[0] == "incr":
                key = command[1]
                self.client.values[key] = str(int(self.client.values.get(key, "0")) + 1)
            elif command[0] == "expire":
                self.client.expirations[command[1]] = command[2]
        return [1 for _ in self.commands]


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.expirations = {}
        self.set_calls = []
        self.deleted = []

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.expirations[key] = ex
        self.set_calls.append((key, value, ex))
        return True

    def delete(self, *keys):
        self.deleted.extend(keys)
        for key in keys:
            self.values.pop(key, None)
        return len(keys)

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakePipeline(self)

    def eval(self, _script, _key_count, generation_key, key, generation, payload, ttl):
        current = self.values.get(generation_key)
        if (current is None and str(generation) == "0") or current == str(generation):
            return int(self.set(key, payload, ex=int(ttl)))
        return 0


class FailingRedis:
    def __getattr__(self, _name):
        def fail(*_args, **_kwargs):
            raise RedisError("redis unavailable")

        return fail


def test_json_cache_hit_miss_and_ttl_are_explicit():
    client = FakeRedis()
    cache = Cache(client)
    key = cache.user_cache_key("habits", 7)
    value = [{"id": 1, "name": "Read", "completed_today": False}]

    assert cache.get_json(key) is None
    assert cache.set_json(key, value, ttl_seconds=45) is True
    assert cache.get_json(key) == value
    assert client.expirations[key] == 45
    assert json.loads(client.set_calls[0][1]) == value


def test_user_and_resource_keys_are_isolated():
    cache = Cache(FakeRedis())

    user_one_list = cache.user_cache_key("habits", 1)
    user_two_list = cache.user_cache_key("habits", 2)
    user_one_detail = cache.user_cache_key("habit", 1, resource_id=9)

    assert len({user_one_list, user_two_list, user_one_detail}) == 3
    assert ":u:1:" in user_one_list
    assert ":u:2:" in user_two_list
    assert user_one_detail.endswith(":r:9")


def test_generation_invalidation_makes_all_old_user_keys_unreachable():
    client = FakeRedis()
    cache = Cache(client)
    old_list_key = cache.user_cache_key("habits", 4)
    old_detail_key = cache.user_cache_key("habit", 4, resource_id=12)
    cache.set_json(old_list_key, [1], ttl_seconds=60)
    cache.set_json(old_detail_key, {"id": 12}, ttl_seconds=60)

    assert cache.invalidate_user_cache(4) is True

    new_list_key = cache.user_cache_key("habits", 4)
    new_detail_key = cache.user_cache_key("habit", 4, resource_id=12)
    assert new_list_key != old_list_key
    assert new_detail_key != old_detail_key
    assert cache.get_json(new_list_key) is None
    assert cache.get_json(new_detail_key) is None
    assert cache.user_cache_key("habits", 5).endswith(":g:0")


def test_conditional_write_cannot_repopulate_after_invalidation():
    client = FakeRedis()
    cache = Cache(client)
    key, generation = cache.user_cache_key_with_generation("habits", 4)
    cache.invalidate_user_cache(4)

    assert cache.set_json_if_generation(
        key, [1], user_id=4, generation=generation, ttl_seconds=60
    ) is False
    assert key not in client.values


@pytest.mark.parametrize("bad_value", ["not-json", '[1, {"broken": ]'])
def test_corrupt_json_is_a_miss_and_is_removed(bad_value):
    client = FakeRedis()
    cache = Cache(client)
    key = cache_key("users")
    client.values[key] = bad_value

    assert cache.get_json(key) is None
    assert key in client.deleted


def test_redis_outage_fails_open_for_reads_writes_and_invalidation():
    cache = Cache(FailingRedis())

    assert cache.get_json(cache_key("users")) is None
    assert cache.set_json(cache_key("users"), [], ttl_seconds=30) is False
    assert cache.delete_keys(cache_key("users")) is False
    assert cache.invalidate_user_cache(3) is False
    assert cache.user_cache_key("habits", 3).endswith(":g:0")


@pytest.mark.parametrize("ttl", [0, -1, 7 * 24 * 60 * 60 + 1])
def test_unbounded_ttls_are_rejected(ttl):
    with pytest.raises(ValueError, match="TTL"):
        Cache(FakeRedis()).set_json(cache_key("users"), [], ttl_seconds=ttl)


def test_cache_ttls_are_configurable_and_bounded(monkeypatch):
    monkeypatch.setenv("CACHE_TTL_SECONDS", "20")
    monkeypatch.setenv("CACHE_HABITS_TTL_SECONDS", "30")
    monkeypatch.setenv("CACHE_USERS_TTL_SECONDS", "40")
    assert CacheTTLs.from_env() == CacheTTLs(default=20, habits=30, users=40)

    monkeypatch.setenv("CACHE_HABITS_TTL_SECONDS", "0")
    with pytest.raises(RuntimeError, match="CACHE_HABITS_TTL_SECONDS"):
        CacheTTLs.from_env()


def test_cache_keys_reject_untrusted_segments_and_invalid_users():
    with pytest.raises(ValueError):
        cache_key("habits:*", user_id=1)
    with pytest.raises(ValueError):
        cache_key("habits", user_id=0)
