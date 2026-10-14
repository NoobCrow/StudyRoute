#!/bin/sh
# Seed the synthetic demo data into a brand-new database (sandbox only), then start the API.
set -eu

if [ "${APP_ENV:-sandbox}" != "production" ]; then
  python -m app.scripts.seed --if-empty
fi

# The API sits behind nginx and is not published to the host, so it may trust the
# X-Forwarded-For header that nginx overwrites. That keeps per-IP rate limits meaningful.
exec uvicorn app.main:create_app --factory \
  --host 0.0.0.0 --port 8000 \
  --proxy-headers --forwarded-allow-ips="*" \
  --no-access-log
