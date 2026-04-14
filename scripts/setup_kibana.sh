#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_kibana.sh  —  Import ResearchLineage Kibana saved objects
#
# Usage:
#   ./scripts/setup_kibana.sh [KIBANA_URL]
#
# Default: KIBANA_URL = http://localhost:5601
#
# Works with or without Elasticsearch/Kibana authentication.
# If ELASTICSEARCH_PASSWORD is set (or present in .env), basic auth is used.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
NDJSON="${ROOT_DIR}/kibana/researchlineage_kibana.ndjson"

KIBANA_URL="${1:-http://localhost:5601}"

# ── Optional auth ─────────────────────────────────────────────────────────────
# Try to load from .env, but don't fail if missing.
if [[ -z "${ELASTICSEARCH_PASSWORD:-}" ]]; then
  ENV_FILE="${ROOT_DIR}/.env"
  if [[ -f "${ENV_FILE}" ]]; then
    PW="$(grep -E '^ELASTICSEARCH_PASSWORD=' "${ENV_FILE}" | cut -d= -f2- | tr -d '"'\''[:space:]' || true)"
    if [[ -n "${PW}" ]]; then
      ELASTICSEARCH_PASSWORD="${PW}"
    fi
  fi
fi

# Build auth flag only when a password is available
AUTH_FLAGS=()
if [[ -n "${ELASTICSEARCH_PASSWORD:-}" ]]; then
  ELASTIC_USER="${ELASTIC_USER:-elastic}"
  AUTH_FLAGS=(-u "${ELASTIC_USER}:${ELASTICSEARCH_PASSWORD}")
  echo "Auth   : ${ELASTIC_USER}:***"
else
  echo "Auth   : none (security disabled)"
fi

echo "Kibana : ${KIBANA_URL}"
echo "File   : ${NDJSON}"
echo

# ── Wait for Kibana to be ready ───────────────────────────────────────────────
echo "Waiting for Kibana to be ready..."
STATUS="000"
for i in $(seq 1 30); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    "${AUTH_FLAGS[@]}" \
    "${KIBANA_URL}/api/status" 2>/dev/null || echo "000")
  if [[ "${STATUS}" == "200" ]]; then
    echo "Kibana is ready."
    break
  fi
  echo "  Attempt ${i}/30 — HTTP ${STATUS}, retrying in 5s..."
  sleep 5
done

if [[ "${STATUS}" != "200" ]]; then
  echo "ERROR: Kibana did not become ready in time (last status: ${STATUS})."
  exit 1
fi

echo

# ── Delete retired objects (old dashboards, visualizations, index patterns) ───
# These were superseded by the Centralized Log Management dashboard.
echo "Removing retired saved objects..."

_delete_obj() {
  local type="$1" id="$2"
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
    "${KIBANA_URL}/api/saved_objects/${type}/${id}?force=true" \
    -H "kbn-xsrf: true" "${AUTH_FLAGS[@]}")
  if [[ "${code}" == "200" ]]; then
    echo "  deleted ${type}/${id}"
  elif [[ "${code}" == "404" ]]; then
    echo "  skip   ${type}/${id} (not found)"
  else
    echo "  warn   ${type}/${id} (HTTP ${code})"
  fi
}

# Retired dashboards
_delete_obj dashboard     rl-dash-overview
_delete_obj dashboard     rl-dash-errors

# Retired visualizations (only used by the deleted dashboards)
_delete_obj visualization rl-viz-log-level
_delete_obj visualization rl-viz-log-volume
_delete_obj visualization rl-viz-top-loggers
_delete_obj visualization rl-viz-error-rate
_delete_obj visualization rl-viz-task-exec
_delete_obj visualization rl-viz-pdf-health
_delete_obj visualization rl-viz-anomalies
_delete_obj visualization rl-viz-papers-depth
_delete_obj visualization rl-viz-airflow
_delete_obj visualization rl-viz-error-count
_delete_obj visualization rl-viz-dag-runs

# Retired saved search
_delete_obj search        rl-search-errors

# Retired index patterns (app-only index no longer needed)
_delete_obj index-pattern rl-idx-app

# Drift dashboard objects (deleted and re-imported fresh on every run)
_delete_obj dashboard     rl-dash-drift
_delete_obj visualization rl-viz-drift-snap-count
_delete_obj visualization rl-viz-drift-live-count
_delete_obj visualization rl-viz-drift-source
_delete_obj visualization rl-viz-drift-snap-year
_delete_obj visualization rl-viz-drift-live-year
_delete_obj visualization rl-viz-drift-snap-depth
_delete_obj visualization rl-viz-drift-live-depth
_delete_obj visualization rl-viz-drift-snap-srctype
_delete_obj visualization rl-viz-drift-live-srctype
_delete_obj visualization rl-viz-drift-fos
_delete_obj visualization rl-viz-drift-snap-terminal
_delete_obj visualization rl-viz-drift-live-terminal
_delete_obj visualization rl-viz-drift-growth
_delete_obj index-pattern rl-idx-drift

# Delete any stray data views created by Filebeat auto-setup or manually
# (identified by title — their IDs are dynamic so we search first)
for _title in "ResearchLineage App" "ResearchLineage Airflow"; do
  _ids=$(curl -s "${AUTH_FLAGS[@]}" \
    "${KIBANA_URL}/api/saved_objects/_find?type=index-pattern&search_fields=title&search=${_title// /+}&per_page=10" \
    | python3 -c "
import json,sys
objs=json.load(sys.stdin).get('saved_objects',[])
print('\n'.join(o['id'] for o in objs if o.get('attributes',{}).get('title','')=='${_title}'))
" 2>/dev/null)
  for _id in ${_ids}; do
    _delete_obj index-pattern "${_id}"
  done
done

# Delete duplicate researchlineage-app-* data views (keep only rl-idx-all)
_dup_ids=$(curl -s "${AUTH_FLAGS[@]}" \
  "${KIBANA_URL}/api/saved_objects/_find?type=index-pattern&search_fields=title&search=researchlineage-app-*&per_page=20" \
  | python3 -c "
import json,sys
objs=json.load(sys.stdin).get('saved_objects',[])
print('\n'.join(o['id'] for o in objs if o.get('attributes',{}).get('title','')=='researchlineage-app-*'))
" 2>/dev/null)
for _id in ${_dup_ids}; do
  _delete_obj index-pattern "${_id}"
done

echo

# ── Import saved objects ──────────────────────────────────────────────────────
# Use a temp file to capture the response body separately from the HTTP code.
# This avoids the 'head -n -1' incompatibility on macOS.
echo "Importing saved objects..."
TMPFILE="$(mktemp)"
trap 'rm -f "${TMPFILE}"' EXIT

HTTP_CODE=$(curl -s -o "${TMPFILE}" -w "%{http_code}" \
  -X POST "${KIBANA_URL}/api/saved_objects/_import?overwrite=true" \
  -H "kbn-xsrf: true" \
  "${AUTH_FLAGS[@]}" \
  -F "file=@${NDJSON}")

BODY="$(cat "${TMPFILE}")"

echo "HTTP ${HTTP_CODE}"

if [[ "${HTTP_CODE}" != "200" ]]; then
  echo "ERROR: Import failed."
  echo "${BODY}" | python3 -m json.tool 2>/dev/null || echo "${BODY}"
  exit 1
fi

# Pretty-print the result summary
echo "${BODY}" | python3 -c "
import json, sys
r = json.load(sys.stdin)
print(f'  success        : {r.get(\"success\", False)}')
print(f'  successCount   : {r.get(\"successCount\", 0)}')
errors = r.get('errors', [])
if errors:
    print(f'  errors ({len(errors)}):')
    for e in errors:
        print(f'    [{e[\"type\"]}] {e[\"id\"]} — {e.get(\"error\", {}).get(\"message\", \"?\")}')
else:
    print('  errors         : none')
" 2>/dev/null || echo "${BODY}"

# ── Raise Discover sample size so log tables show up to 10 000 rows ──────────
echo "Setting discover:sampleSize → 10000..."
SETTINGS_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${KIBANA_URL}/api/kibana/settings" \
  -H "kbn-xsrf: true" \
  -H "Content-Type: application/json" \
  "${AUTH_FLAGS[@]}" \
  -d '{"changes":{"discover:sampleSize":10000}}')
if [[ "${SETTINGS_CODE}" == "200" ]]; then
  echo "  discover:sampleSize = 10000 ✓"
else
  echo "  WARNING: could not set sample size (HTTP ${SETTINGS_CODE})."
  echo "  Set it manually: Stack Management → Advanced Settings → discover:sampleSize"
fi

echo
echo "Done. Open Kibana:"
echo "  Dashboards : ${KIBANA_URL}/app/dashboards"
echo "  Discover   : ${KIBANA_URL}/app/discover"
