from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from redis.exceptions import RedisError

from .auth import validate_auth_configuration
from .database import engine
from .habits import router as habits_router
from .logging_config import RequestContextMiddleware, configure_logging
from .metrics import (
    MetricsMiddleware,
    metrics_response,
    metrics_settings,
    record_readiness,
)
from .redis_client import redis_client
from .security import SecurityHeadersMiddleware, csv_env, max_request_bytes

configure_logging()
validate_auth_configuration()
app = FastAPI(title="Habit Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=csv_env(
        "CORS_ALLOWED_ORIGINS",
        ("http://localhost:3000", "http://127.0.0.1:3000"),
    ),
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-User-Id", "X-Auth-Token"],
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=csv_env(
        "ALLOWED_HOSTS",
        ("localhost", "127.0.0.1", "backend", "testserver"),
    ),
)
app.add_middleware(SecurityHeadersMiddleware, request_limit=max_request_bytes())
app.add_middleware(MetricsMiddleware, enabled=metrics_settings.enabled)
# Starlette wraps middleware in reverse registration order. Request context is
# intentionally outermost so even trusted-host/body-limit rejections are
# correlated and receive X-Request-ID.
app.add_middleware(RequestContextMiddleware)

app.include_router(habits_router)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def readiness():
    """Report whether required dependencies can serve real traffic."""
    failures: list[str] = []
    database_ok = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        database_ok = False
        failures.append("database")
    redis_ok = True
    try:
        redis_client.ping()
    except RedisError:
        redis_ok = False
        failures.append("redis")

    record_readiness(database_ok=database_ok, redis_ok=redis_ok)

    if failures:
        # Names are useful to orchestration while exceptions (which may expose
        # credentials or topology) intentionally remain out of the response.
        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=503,
            content={"status": "not ready", "unavailable": failures},
        )
    return {"status": "ready"}


@app.get("/metrics", include_in_schema=False)
def metrics(request: Request):
    return metrics_response(request)
