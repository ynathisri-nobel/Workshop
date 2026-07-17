#!/usr/bin/env bash
# Start the CRM Knowledge Assistant.
set -e
cd "$(dirname "$0")"
export AWS_REGION="${AWS_REGION:-us-east-1}"
./.venv/bin/python -m app.seed || true
exec ./.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
