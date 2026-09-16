"""Central, secret-safe logging configuration.

Application logs intentionally use an allow-list of structured fields.  This
keeps credentials, request bodies, email addresses, service URLs and SQL
parameters out of logs even when callers accidentally attach them as extras.
"""

from __future__ import annotations

import contextvars
import json
import logging
import os
import re
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any


_request_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "request_id", default="-"
)
_SAFE_FIELDS = {
    "event",
    "component",
    "operation",
    "outcome",
    "duration_ms",
    "status_code",
    "cache_result",
    "dependency",
    "task",
    "reason",
    "method",
    "route",
    "transport",
    "exception_type",
}
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
_SENSITIVE_TEXT = re.compile(
    r"(?i)(?:postgresql|redis|rediss)://\S+|\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b|"
    r"(?:x-auth-token|auth_secret|password|secret)\s*[=:]\s*\S+"
)


def _safe_message(value: str) -> str:
    return _SENSITIVE_TEXT.sub("[REDACTED]", value)


def set_request_id(value: str) -> contextvars.Token[str]:
    """Bind a validated correlation identifier to the current async context."""

    safe = value if _REQUEST_ID_PATTERN.fullmatch(value) else "-"
    return _request_id.set(safe)


def reset_request_id(token: contextvars.Token[str]) -> None:
    _request_id.reset(token)


def get_request_id() -> str:
    return _request_id.get()


class SafeJsonFormatter(logging.Formatter):
    """One-line JSON formatter which serializes only explicitly safe fields."""

    def format(self, record: logging.LogRecord) -> str:
        document: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": _safe_message(record.getMessage()),
            "request_id": get_request_id(),
        }
        for field in _SAFE_FIELDS:
            value = getattr(record, field, None)
            if isinstance(value, (str, int, float, bool)) and value != "":
                document[field] = value
        # Exception text can contain URLs, SQL parameters or user data.  The
        # type is sufficient for operations while details stay server-private.
        if record.exc_info and record.exc_info[0]:
            document["exception_type"] = record.exc_info[0].__name__
        return json.dumps(document, ensure_ascii=True, separators=(",", ":"))


class DevFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        event = getattr(record, "event", "")
        suffix = f" event={event}" if event else ""
        return (
            f"{record.levelname:<8} {record.name} [{get_request_id()}] "
            f"{record.getMessage()}{suffix}"
        )


def configure_logging() -> None:
    """Configure the process once; production output is machine-readable."""

    production = os.environ.get("APP_ENV", "development").lower() in {
        "prod",
        "production",
        "staging",
    }
    level = os.environ.get("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        level = "INFO"
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(SafeJsonFormatter() if production else DevFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # The application access event uses normalized route templates.  Uvicorn's
    # default access logger includes raw paths/query strings and would duplicate
    # every request.
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


class WarningThrottle:
    """Process-local suppression for repetitive dependency outage warnings."""

    def __init__(self, interval_seconds: float = 60.0) -> None:
        self._interval = interval_seconds
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()

    def should_log(self, event: str) -> bool:
        now = time.monotonic()
        with self._lock:
            previous = self._last.get(event, 0.0)
            if now - previous < self._interval:
                return False
            self._last[event] = now
            return True


dependency_warning_throttle = WarningThrottle()


def log_dependency_warning(
    logger: logging.Logger, event: str, *, dependency: str, operation: str
) -> None:
    if dependency_warning_throttle.should_log(event):
        logger.warning(
            "Dependency operation failed; degraded behavior enabled",
            extra={
                "event": event,
                "component": dependency,
                "dependency": dependency,
                "operation": operation,
                "outcome": "degraded",
            },
        )


class RequestContextMiddleware:
    """Pure ASGI request correlation and sanitized access logging.

    Install this as the outermost application middleware so rejected requests
    and responses from all other middleware receive the same correlation ID.
    Raw paths, query strings, client addresses, headers, and bodies are never
    recorded.  A matched route template (for example ``/habits/{habit_id}``)
    is safe to aggregate and avoids high-cardinality logs.
    """

    def __init__(self, app: Any) -> None:
        self.app = app
        self.logger = logging.getLogger("app.access")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        import uuid

        incoming = ""
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-request-id":
                incoming = value.decode("ascii", errors="ignore")
                break
        request_id = incoming if _REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        token = set_request_id(request_id)
        status_code = 500
        started = time.monotonic()

        async def send_with_request_id(message: dict[str, Any]) -> None:
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status", 500))
                headers = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() != b"x-request-id"
                ]
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            self.logger.error(
                "Unhandled request failure",
                extra={
                    "event": "request_exception",
                    "outcome": "error",
                    "exception_type": type(exc).__name__,
                },
            )
            raise
        finally:
            route_object = scope.get("route")
            route = getattr(route_object, "path", "unmatched")
            self.logger.info(
                "Request completed",
                extra={
                    "event": "http_request",
                    "method": str(scope.get("method", "UNKNOWN")),
                    "route": route,
                    "status_code": status_code,
                    "duration_ms": round((time.monotonic() - started) * 1000, 2),
                    "outcome": "success" if status_code < 500 else "error",
                    "transport": "http",
                },
            )
            reset_request_id(token)
