import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from unittest.mock import MagicMock

from app.auth import issue_compatibility_token, validate_auth_configuration, verify_identity_token
from app.habits import get_current_user_id
from app.schemas import OnboardingComplete
from app.security import SecurityHeadersMiddleware, csv_env


def test_user_id_must_be_positive():
    with pytest.raises(Exception) as error:
        get_current_user_id(0)
    assert error.value.status_code == 400


def test_csv_env_strips_empty_values(monkeypatch):
    monkeypatch.setenv("TEST_ALLOWLIST", " https://one.example, ,https://two.example ")
    assert csv_env("TEST_ALLOWLIST", ()) == [
        "https://one.example",
        "https://two.example",
    ]


def test_security_headers_and_request_limit():
    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    async def invoke(content_length: int):
        messages = []
        scope = {
            "type": "http",
            "method": "POST",
            "path": "/habits",
            "scheme": "https",
            "headers": [(b"content-length", str(content_length).encode())],
        }

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        async def send(message):
            messages.append(message)

        app = SecurityHeadersMiddleware(downstream, request_limit=10)
        await app(scope, receive, send)
        return messages

    allowed = asyncio.run(invoke(10))
    allowed_headers = dict(allowed[0]["headers"])
    assert allowed[0]["status"] == 200
    assert allowed_headers[b"x-content-type-options"] == b"nosniff"
    assert b"strict-transport-security" in allowed_headers

    rejected = asyncio.run(invoke(11))
    rejected_headers = dict(rejected[0]["headers"])
    assert rejected[0]["status"] == 413
    assert rejected_headers[b"x-frame-options"] == b"DENY"


def test_chunked_request_body_is_limited_before_downstream():
    called = False

    async def downstream(scope, receive, send):
        nonlocal called
        called = True

    async def invoke():
        chunks = iter(
            [
                {"type": "http.request", "body": b"123456", "more_body": True},
                {"type": "http.request", "body": b"78901", "more_body": False},
            ]
        )
        sent = []

        async def receive():
            return next(chunks)

        async def send(message):
            sent.append(message)

        scope = {"type": "http", "method": "POST", "path": "/habits", "scheme": "http", "headers": []}
        await SecurityHeadersMiddleware(downstream, request_limit=10)(scope, receive, send)
        return sent

    messages = asyncio.run(invoke())
    assert messages[0]["status"] == 413
    assert called is False


def test_production_identity_requires_valid_credential(monkeypatch):
    secret = "s" * 32
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET", secret)

    token = issue_compatibility_token(7)
    verify_identity_token(7, token)

    with pytest.raises(HTTPException) as missing:
        verify_identity_token(7, None)
    assert missing.value.status_code == 401

    with pytest.raises(HTTPException) as invalid:
        verify_identity_token(7, issue_compatibility_token(8))
    assert invalid.value.status_code == 403


def test_production_auth_configuration_rejects_weak_secret(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_SECRET", "too-short")
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        validate_auth_configuration()


def test_unknown_user_is_a_controlled_404(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None

    with pytest.raises(HTTPException) as error:
        get_current_user_id(999, None, db)
    assert error.value.status_code == 404
    assert error.value.detail == "User not found"


def test_onboarding_version_matches_postgres_integer_range():
    assert OnboardingComplete(version=2_147_483_647).version == 2_147_483_647
    with pytest.raises(ValidationError):
        OnboardingComplete(version=2_147_483_648)
