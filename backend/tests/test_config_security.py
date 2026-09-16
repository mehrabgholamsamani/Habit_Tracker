import pytest

from app.config import load_settings


def test_production_requires_explicit_service_urls(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)

    with pytest.raises(RuntimeError, match="DATABASE_URL must be set"):
        load_settings()


def test_unknown_environment_is_rejected(monkeypatch):
    monkeypatch.setenv("APP_ENV", "produciton")

    with pytest.raises(RuntimeError, match="APP_ENV must be one of"):
        load_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DATABASE_URL", "sqlite:///local.db"),
        ("REDIS_URL", "http://redis:6379/0"),
    ],
)
def test_service_urls_reject_unexpected_schemes(monkeypatch, name, value):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv(name, value)

    with pytest.raises(RuntimeError, match="unsupported URL scheme"):
        load_settings()
