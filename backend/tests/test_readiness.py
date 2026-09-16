import json

from starlette.responses import JSONResponse

from app.main import health, readiness


def test_health_is_liveness_and_does_not_probe_dependencies():
    assert health() == {"status": "ok"}


def test_readiness_reports_dependencies(monkeypatch):
    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, _query):
            return None

    monkeypatch.setattr("app.main.engine.connect", lambda: Connection())
    monkeypatch.setattr("app.main.redis_client.ping", lambda: True)

    assert readiness() == {"status": "ready"}


def test_readiness_returns_503_without_leaking_exception(monkeypatch):
    def unavailable():
        raise RuntimeError("postgresql://secret@private-host/database")

    monkeypatch.setattr("app.main.engine.connect", unavailable)
    monkeypatch.setattr("app.main.redis_client.ping", lambda: True)

    response = readiness()
    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert json.loads(response.body) == {
        "status": "not ready",
        "unavailable": ["database"],
    }
    assert b"secret" not in response.body
