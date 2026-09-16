import asyncio
import json
import logging

from app.logging_config import RequestContextMiddleware, SafeJsonFormatter, set_request_id, reset_request_id


def test_json_formatter_is_structured_and_redacts_sensitive_values():
    formatter = SafeJsonFormatter()
    token = set_request_id("req-safe_1")
    try:
        record = logging.LogRecord(
            "app.test", logging.WARNING, __file__, 1,
            "failed redis://user:password@redis:6379/0 for person@example.com",
            (), None,
        )
        record.event = "dependency_error"
        record.auth_secret = "must-not-appear"
        output = formatter.format(record)
    finally:
        reset_request_id(token)

    parsed = json.loads(output)
    assert parsed["request_id"] == "req-safe_1"
    assert parsed["event"] == "dependency_error"
    assert "redis://" not in output
    assert "person@example.com" not in output
    assert "must-not-appear" not in output


def test_request_middleware_rejects_unsafe_id_and_adds_generated_id(caplog):
    async def downstream(scope, receive, send):
        class Route:
            path = "/habits/{habit_id}"
        scope["route"] = Route()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def invoke():
        sent = []
        scope = {
            "type": "http", "method": "GET", "path": "/habits/123",
            "headers": [(b"x-request-id", b"unsafe\r\nid")],
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await RequestContextMiddleware(downstream)(scope, receive, send)
        return sent

    with caplog.at_level(logging.INFO, logger="app.access"):
        messages = asyncio.run(invoke())
    response_headers = dict(messages[0]["headers"])
    request_id = response_headers[b"x-request-id"].decode()
    assert request_id != "unsafe\r\nid"
    assert len(request_id) == 32
    access = next(record for record in caplog.records if record.event == "http_request")
    assert access.route == "/habits/{habit_id}"
    assert access.status_code == 200


def test_request_middleware_preserves_sane_request_id():
    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def invoke():
        sent = []
        scope = {"type": "http", "method": "GET", "headers": [(b"x-request-id", b"client-123")]}

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            sent.append(message)

        await RequestContextMiddleware(downstream)(scope, receive, send)
        return sent

    messages = asyncio.run(invoke())
    assert dict(messages[0]["headers"])[b"x-request-id"] == b"client-123"
