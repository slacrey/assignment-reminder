#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.napcat}"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "Missing env file: $ENV_FILE" >&2
  echo "Create it from .env.napcat.example first." >&2
  exit 1
fi

export QQ_SENDER="${QQ_SENDER:-onebot}"
export ONEBOT_BASE_URL="${ONEBOT_BASE_URL:-http://127.0.0.1:3000}"
export ONEBOT_TIMEOUT_SECONDS="${ONEBOT_TIMEOUT_SECONDS:-5}"

HOST="${UVICORN_HOST:-127.0.0.1}"
PORT="${UVICORN_PORT:-8000}"

cd "$ROOT_DIR"

echo "Starting assignment-reminder with QQ_SENDER=$QQ_SENDER"
echo "OneBot gateway: $ONEBOT_BASE_URL"
echo "Management page: http://$HOST:$PORT"

uv run uvicorn app.main:app --reload --host "$HOST" --port "$PORT"
