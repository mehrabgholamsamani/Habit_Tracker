import os
from dataclasses import dataclass

from sqlalchemy.engine import URL, make_url


_DEVELOPMENT_DATABASE_URL = "postgresql://habit:habit@postgres:5432/habit_tracker"
_DEVELOPMENT_REDIS_URL = "redis://redis:6379/0"
_PRODUCTION_ENVIRONMENTS = {"prod", "production"}
_VALID_ENVIRONMENTS = {"development", "test", "staging", *_PRODUCTION_ENVIRONMENTS}


def _environment() -> str:
    value = os.environ.get("APP_ENV", "development").strip().lower()
    if value not in _VALID_ENVIRONMENTS:
        raise RuntimeError(
            "APP_ENV must be one of development, test, staging, prod, or production"
        )
    return value


def _service_url(name: str, development_default: str, allowed_schemes: set[str]) -> str:
    value = os.environ.get(name)
    if not value:
        if _environment() in _PRODUCTION_ENVIRONMENTS:
            raise RuntimeError(f"{name} must be set when APP_ENV is production")
        value = development_default

    try:
        parsed: URL = make_url(value)
    except Exception as exc:
        raise RuntimeError(f"{name} is not a valid URL") from exc

    if parsed.drivername.split("+", 1)[0] not in allowed_schemes:
        raise RuntimeError(f"{name} uses an unsupported URL scheme")
    return value


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise RuntimeError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class Settings:
    database_url: str
    redis_url: str
    database_pool_size: int = 10
    database_max_overflow: int = 10
    database_pool_timeout_seconds: int = 10
    database_statement_timeout_ms: int = 15_000
    database_lock_timeout_ms: int = 5_000


def load_settings() -> Settings:
    # Validate even when every service URL is explicitly supplied; otherwise a
    # misspelled production environment silently receives development policy.
    _environment()
    return Settings(
        database_url=_service_url(
            "DATABASE_URL", _DEVELOPMENT_DATABASE_URL, {"postgresql"}
        ),
        redis_url=_service_url("REDIS_URL", _DEVELOPMENT_REDIS_URL, {"redis", "rediss"}),
        database_pool_size=_bounded_int("DATABASE_POOL_SIZE", 10, 1, 100),
        database_max_overflow=_bounded_int("DATABASE_MAX_OVERFLOW", 10, 0, 100),
        database_pool_timeout_seconds=_bounded_int(
            "DATABASE_POOL_TIMEOUT_SECONDS", 10, 1, 120
        ),
        database_statement_timeout_ms=_bounded_int(
            "DATABASE_STATEMENT_TIMEOUT_MS", 15_000, 100, 300_000
        ),
        database_lock_timeout_ms=_bounded_int(
            "DATABASE_LOCK_TIMEOUT_MS", 5_000, 100, 300_000
        ),
    )


settings = load_settings()
