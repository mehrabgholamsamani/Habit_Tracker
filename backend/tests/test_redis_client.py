from redis.exceptions import RedisError

from app import redis_client as module


class FakeRedis:
    def __init__(self, result=1):
        self.result = result
        self.calls = []

    def eval(self, *args):
        self.calls.append(args)
        return self.result


def test_rate_limit_is_one_atomic_redis_operation(monkeypatch):
    client = FakeRedis(result=3)
    monkeypatch.setattr(module, "redis_client", client)

    assert module.check_rate_limit(7, "checkin", 3, 60) is True
    assert len(client.calls) == 1
    assert "INCR" in client.calls[0][0]
    assert "EXPIRE" in client.calls[0][0]


def test_rate_limit_fails_open_when_redis_is_unavailable(monkeypatch):
    class DownRedis:
        def eval(self, *_args):
            raise RedisError("down")

    monkeypatch.setattr(module, "redis_client", DownRedis())
    assert module.check_rate_limit(7) is True


def test_rate_limit_rejects_invalid_arguments():
    try:
        module.check_rate_limit(0)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid user id was accepted")
