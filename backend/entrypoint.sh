#!/bin/sh
set -e

python -c "
import os
import time
from sqlalchemy import create_engine

url = os.environ.get('DATABASE_URL')
for attempt in range(30):
    try:
        create_engine(url).connect().close()
        break
    except Exception:
        # Connection errors can contain credentials or infrastructure details.
        print('database not ready yet, retrying...')
        time.sleep(1)
else:
    raise SystemExit('database never became available')
"

environment="${APP_ENV:-development}"
run_migrations="${RUN_MIGRATIONS:-}"
run_seed="${RUN_SEED:-}"
if [ -z "$run_migrations" ]; then
    [ "$environment" = "development" ] && run_migrations=true || run_migrations=false
fi
if [ -z "$run_seed" ]; then
    [ "$environment" = "development" ] && run_seed=true || run_seed=false
fi

# Development remains zero-setup. Production deployments should normally run
# migrations/seeding as a one-off release job and set these flags to false on
# every API replica. The startup helper also serializes accidental concurrent
# migration/seed attempts with a PostgreSQL advisory lock.
if [ "$run_migrations" = "true" ]; then
    python -m app.startup migrate
fi
if [ "$run_seed" = "true" ]; then
    python -m app.startup seed
fi

if [ "$environment" = "development" ]; then
    exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --reload-dir app
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 \
    --workers "${WEB_CONCURRENCY:-1}" --proxy-headers \
    --forwarded-allow-ips "${FORWARDED_ALLOW_IPS:-127.0.0.1}"
