#!/usr/bin/env bash
set -euo pipefail
# Push variables from .env into Railway via GraphQL API
# Usage: bash scripts/deploy_to_railway.sh --token $RAILWAY_API_TOKEN --project $PROJECT_ID --environment $ENVIRONMENT_ID [--service $SERVICE_ID]

help(){ sed -n '1,80p' "$0"; }

TOKEN=""; PROJECT=""; ENV_ID=""; SERVICE="";
while [[ $# -gt 0 ]]; do
  case "$1" in
    --token) TOKEN="$2"; shift 2;;
    --project) PROJECT="$2"; shift 2;;
    --environment) ENV_ID="$2"; shift 2;;
    --service) SERVICE="$2"; shift 2;;
    -h|--help) help; exit 0;;
    *) echo "Unknown arg: $1"; help; exit 1;;
  esac
done

if [[ -z "$TOKEN" || -z "$PROJECT" || -z "$ENV_ID" ]]; then
  echo "Missing required args"; help; exit 1
fi

python3 scripts/railway_set_vars.py \
  --token "$TOKEN" \
  --project "$PROJECT" \
  --environment "$ENV_ID" \
  ${SERVICE:+--service "$SERVICE"} \
  --env-file .env

echo "All done. Open Railway → your service → Deployments to watch rollout."
