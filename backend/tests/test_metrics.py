import asyncio
from types import SimpleNamespace

import pytest
from starlette.requests import Request

from app import metrics


def test_metrics_configuration_is_safe_in_production(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="METRICS_TOKEN"):
        metrics.load_metrics_settings()

    monkeypatch.setenv("METRICS_TOKEN", "x" * 32)
    assert metrics.load_metrics_settings().enabled is True


def test_metrics_configuration_rejects_ambiguous_boolean(monkeypatch):
    monkeypatch.setenv("METRICS_ENABLED", "sometimes")
    with pytest.raises(RuntimeError, match="must be a boolean"):
        metrics.load_metrics_settings()


def test_metrics_require_one_worker(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("METRICS_ENABLED", "true")
    monkeypatch.setenv("WEB_CONCURRENCY", "2")
    with pytest.raises(RuntimeError, match="WEB_CONCURRENCY must be 1"):
        metrics.load_metrics_settings()


def test_metrics_endpoint_requires_token_and_exposes_prometheus(monkeypatch):
    monkeypatch.setattr(metrics, "metrics_settings", metrics.MetricsSettings(True, "s" * 32))
    unauthorized = metrics.metrics_response(Request({"type": "http", "headers": []}))
    assert unauthorized.status_code == 401

    request = Request(
        {
            "type": "http",
            "headers": [(b"authorization", b"Bearer " + b"s" * 32)],
        }
    )
    response = metrics.metrics_response(request)
    assert response.status_code == 200
    assert b"habit_tracker_http_requests_total" in response.body


def test_http_middleware_uses_route_template_not_raw_path():
    async def endpoint(scope, receive, send):
        scope["route"] = SimpleNamespace(path="/habits/{habit_id}")
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    middleware = metrics.MetricsMiddleware(endpoint)
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/habits/sensitive-user-value",
        "headers": [],
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        pass

    asyncio.run(middleware(scope, receive, send))
    output = metrics.generate_latest(metrics.registry)
    assert b'route="/habits/{habit_id}"' in output
    assert b"sensitive-user-value" not in output


def test_readiness_metrics_have_bounded_dependency_labels():
    metrics.record_readiness(database_ok=True, redis_ok=False)
    output = metrics.generate_latest(metrics.registry)
    assert b'habit_tracker_dependency_ready{dependency="database"} 1.0' in output
    assert b'habit_tracker_dependency_ready{dependency="redis"} 0.0' in output
    assert b'habit_tracker_readiness_checks_total{result="not_ready"}' in output


def test_untrusted_http_methods_collapse_to_bounded_label():
    assert metrics._method_label("GET") == "GET"
    assert metrics._method_label("ATTACKER-CONTROLLED") == "OTHER"
