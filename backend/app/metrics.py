"""Low-cardinality Prometheus metrics for the Habit Tracker service."""

from __future__ import annotations

import hmac
import os
import time
from dataclasses import dataclass

from fastapi import Request
from fastapi.responses import PlainTextResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _boolean_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean")


@dataclass(frozen=True)
class MetricsSettings:
    enabled: bool
    token: str | None


def load_metrics_settings() -> MetricsSettings:
    production = os.getenv("APP_ENV", "development").strip().lower() in {"prod", "production"}
    enabled = _boolean_env("METRICS_ENABLED", not production)
    token = os.getenv("METRICS_TOKEN") or None
    if enabled and production and (token is None or len(token.encode()) < 32):
        raise RuntimeError(
            "METRICS_TOKEN must be at least 32 bytes when metrics are enabled in production"
        )
    if enabled:
        try:
            workers = int(os.getenv("WEB_CONCURRENCY", "1"))
        except ValueError as exc:
            raise RuntimeError("WEB_CONCURRENCY must be an integer") from exc
        if workers != 1:
            raise RuntimeError(
                "WEB_CONCURRENCY must be 1 when in-process metrics are enabled; scale with replicas"
            )
    return MetricsSettings(enabled=enabled, token=token)


metrics_settings = load_metrics_settings()
registry = CollectorRegistry()

HTTP_REQUESTS = Counter(
    "habit_tracker_http_requests_total",
    "Completed HTTP requests.",
    ("method", "route", "status_class"),
    registry=registry,
)
HTTP_DURATION = Histogram(
    "habit_tracker_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5),
    registry=registry,
)
HTTP_IN_FLIGHT = Gauge(
    "habit_tracker_http_requests_in_flight",
    "Currently executing HTTP requests.",
    ("method",),
    registry=registry,
)
DEPENDENCY_READY = Gauge(
    "habit_tracker_dependency_ready",
    "Whether a required dependency passed its latest readiness probe.",
    ("dependency",),
    registry=registry,
)
READINESS_CHECKS = Counter(
    "habit_tracker_readiness_checks_total",
    "Readiness checks by overall result.",
    ("result",),
    registry=registry,
)
CACHE_OPERATIONS = Counter(
    "habit_tracker_cache_operations_total",
    "Cache operations by bounded operation and outcome.",
    ("operation", "result"),
    registry=registry,
)
RATE_LIMIT_DECISIONS = Counter(
    "habit_tracker_rate_limit_decisions_total",
    "Rate-limit decisions by bounded outcome.",
    ("result",),
    registry=registry,
)

_CACHE_OPERATIONS = {"get", "set", "delete", "invalidate"}
_CACHE_RESULTS = {"hit", "miss", "success", "error", "rejected"}
_RATE_LIMIT_RESULTS = {"allowed", "limited", "fail_open"}


def record_cache(operation: str, result: str) -> None:
    """Record cache behavior while enforcing a fixed label vocabulary."""
    if operation not in _CACHE_OPERATIONS or result not in _CACHE_RESULTS:
        raise ValueError("unsupported cache metric label")
    CACHE_OPERATIONS.labels(operation=operation, result=result).inc()


def record_rate_limit(result: str) -> None:
    if result not in _RATE_LIMIT_RESULTS:
        raise ValueError("unsupported rate-limit metric label")
    RATE_LIMIT_DECISIONS.labels(result=result).inc()


def record_readiness(*, database_ok: bool, redis_ok: bool) -> None:
    DEPENDENCY_READY.labels(dependency="database").set(int(database_ok))
    DEPENDENCY_READY.labels(dependency="redis").set(int(redis_ok))
    READINESS_CHECKS.labels(result="ready" if database_ok and redis_ok else "not_ready").inc()


def _route_template(scope: Scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    # Only framework-owned route templates are safe labels. Never fall back to
    # the requested path because it may contain IDs, tokens, or arbitrary text.
    return path if isinstance(path, str) else "__unmatched__"


def _method_label(method: object) -> str:
    value = str(method).upper()
    return value if value in {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"} else "OTHER"


class MetricsMiddleware:
    def __init__(self, app: ASGIApp, enabled: bool = True) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope["type"] != "http" or scope.get("path") == "/metrics":
            await self.app(scope, receive, send)
            return

        method = _method_label(scope.get("method", "UNKNOWN"))
        status_code = 500
        started = time.perf_counter()
        HTTP_IN_FLIGHT.labels(method=method).inc()

        async def capture_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, capture_status)
        finally:
            route = _route_template(scope)
            HTTP_IN_FLIGHT.labels(method=method).dec()
            HTTP_REQUESTS.labels(
                method=method, route=route, status_class=f"{status_code // 100}xx"
            ).inc()
            HTTP_DURATION.labels(method=method, route=route).observe(
                time.perf_counter() - started
            )


def metrics_response(request: Request) -> Response:
    if not metrics_settings.enabled:
        return PlainTextResponse("Not Found", status_code=404)

    if metrics_settings.token is not None:
        authorization = request.headers.get("authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        valid = separator and scheme.lower() == "bearer" and hmac.compare_digest(
            supplied.encode(), metrics_settings.token.encode()
        )
        if not valid:
            return PlainTextResponse("Unauthorized", status_code=401)

    return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
