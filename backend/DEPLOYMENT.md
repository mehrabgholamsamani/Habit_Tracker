# Backend deployment

The Compose setup is the development profile: leaving `APP_ENV` unset preserves
automatic migrations, idempotent seed data, and Uvicorn reload.

For production API replicas, configure at least:

```text
APP_ENV=production
DATABASE_URL=postgresql://...
REDIS_URL=rediss://...
AUTH_SECRET=<at least 32 random bytes>
ALLOWED_HOSTS=api.example.com
CORS_ALLOWED_ORIGINS=https://app.example.com
FORWARDED_ALLOW_IPS=<address or CIDR of the trusted reverse proxy>
RUN_MIGRATIONS=false
RUN_SEED=false
WEB_CONCURRENCY=1
METRICS_ENABLED=true
METRICS_TOKEN=<at least 32 random bytes>
```

Never set `FORWARDED_ALLOW_IPS=*` on an internet-reachable container. HSTS is
emitted only when the request scheme is HTTPS, so forwarded headers must be
accepted exclusively from the trusted TLS-terminating proxy.

Run schema changes once as a release job before rolling API replicas:

```sh
APP_ENV=production python -m app.startup migrate
```

If multiple release jobs are accidentally started, `app.startup` serializes
them using a PostgreSQL session advisory lock. Production does not seed data by
default; explicitly run `python -m app.startup seed` only when intended.

Use `GET /health` as the process liveness probe. Use `GET /ready` as the traffic
readiness probe; it returns HTTP 503 and names unavailable required dependencies
without exposing connection exceptions.

Prometheus metrics are disabled by default in production. When enabled, scrape
`GET /metrics` with `Authorization: Bearer <METRICS_TOKEN>`. Metrics are held in
process, so `WEB_CONCURRENCY` must remain `1`; scale horizontally with multiple
container replicas and configure Prometheus to scrape every replica. This keeps
each time series complete without a shared multiprocess filesystem.
