#!/bin/sh
set -e

START='if [ "${OTEL_SDK_DISABLED:-true}" = "false" ]; then exec opentelemetry-instrument uvicorn main:app --host 0.0.0.0 --port 8000; fi; exec uvicorn main:app --host 0.0.0.0 --port 8000'

if [ -n "${INFISICAL_CLIENT_ID:-}" ] && [ -n "${INFISICAL_CLIENT_SECRET:-}" ]; then
  INFISICAL_TOKEN=$(infisical login --method=universal-auth \
    --client-id="$INFISICAL_CLIENT_ID" \
    --client-secret="$INFISICAL_CLIENT_SECRET" \
    --silent --plain)

  exec infisical run \
    --token="$INFISICAL_TOKEN" \
    --projectId=2296d19c-5f3b-41e1-afa3-fcde39966a71 \
    --env="${INFISICAL_ENV:-qa}" \
    --path=/ \
    -- sh -c "$START"
fi

exec sh -c "$START"
