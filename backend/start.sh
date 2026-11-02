#!/bin/sh
set -eu

if [ -n "${FRONTEND_HOSTNAME:-}" ]; then
  FRONTEND_URL=${FRONTEND_URL:-"https://${FRONTEND_HOSTNAME}"}
  CORS_ORIGINS=${CORS_ORIGINS:-"$FRONTEND_URL"}
  STRIPE_RETURN_ORIGINS=${STRIPE_RETURN_ORIGINS:-"$FRONTEND_URL"}
  export FRONTEND_URL CORS_ORIGINS STRIPE_RETURN_ORIGINS
fi

APP_VERSION=${APP_VERSION:-${RENDER_GIT_COMMIT:-}}
export APP_VERSION

case "${ENVIRONMENT:-}" in
  production|prod|staging|development|dev|test)
    # Toujours valider la configuration, y compris en développement : un
    # ENVIRONMENT absent ou mal orthographié ne doit jamais démarrer l'app.
    python /app/backend/preflight.py
    ;;
  *)
    echo "ENVIRONMENT must be explicitly set to production, staging, development or test" >&2
    exit 1
    ;;
esac

PORT=${PORT:-8000}
exec python -m uvicorn backend.server:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1 \
  --no-access-log
