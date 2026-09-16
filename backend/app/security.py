import os
from collections.abc import Iterable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


DEFAULT_MAX_REQUEST_BYTES = 64 * 1024


def csv_env(name: str, default: Iterable[str]) -> list[str]:
    """Read a comma-separated allowlist, ignoring whitespace and empty entries."""
    raw = os.getenv(name)
    if raw is None:
        return list(default)
    return [value.strip() for value in raw.split(",") if value.strip()]


def max_request_bytes() -> int:
    raw = os.getenv("MAX_REQUEST_BYTES", str(DEFAULT_MAX_REQUEST_BYTES))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("MAX_REQUEST_BYTES must be an integer") from exc
    if value < 1:
        raise RuntimeError("MAX_REQUEST_BYTES must be greater than zero")
    return value


class SecurityHeadersMiddleware:
    """Add browser hardening headers and reject oversized request bodies.

    This is a small pure-ASGI middleware so headers are also attached to error
    responses. The web app's endpoint payloads are not modified.
    """

    def __init__(self, app: ASGIApp, request_limit: int) -> None:
        self.app = app
        self.request_limit = request_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
                too_large = declared_length < 0 or declared_length > self.request_limit
            except ValueError:
                too_large = True
            if too_large:
                response = JSONResponse(status_code=413, content={"detail": "Request body too large"})
                await response(scope, receive, self._secure_send(send, scope))
                return

        # Do not rely on Content-Length: HTTP/1.1 chunked bodies and HTTP/2 do
        # not need to declare it. Buffer only up to the configured small limit,
        # then replay the body to Starlette.
        messages: list[Message] = []
        received = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            received += len(message.get("body", b""))
            if received > self.request_limit:
                response = JSONResponse(
                    status_code=413, content={"detail": "Request body too large"}
                )
                await response(scope, receive, self._secure_send(send, scope))
                return
            messages.append(message)
            if not message.get("more_body", False):
                break

        index = 0

        async def replay_receive() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        await self.app(scope, replay_receive, self._secure_send(send, scope))

    @staticmethod
    def _secure_send(send: Send, scope: Scope) -> Send:
        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers.setdefault("x-content-type-options", "nosniff")
                headers.setdefault("x-frame-options", "DENY")
                headers.setdefault("referrer-policy", "no-referrer")
                headers.setdefault("permissions-policy", "camera=(), microphone=(), geolocation=()")
                headers.setdefault("content-security-policy", "default-src 'none'; frame-ancestors 'none'")
                headers.setdefault("cache-control", "no-store")
                if scope.get("scheme") == "https":
                    headers.setdefault("strict-transport-security", "max-age=31536000; includeSubDomains")
            await send(message)

        return send_with_headers
