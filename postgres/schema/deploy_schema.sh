#!/usr/bin/env bash
# =============================================================================
# ResearchLineage — deploy_schema.sh
# Deploys the full PostgreSQL schema to a target database.
# =============================================================================
set -euo pipefail

# ── Configuration ─────────────────────────────────────────────────────────────
# Set DB_URL via environment variable or edit the default below.
# Format: postgresql://USER:PASSWORD@HOST:PORT/DBNAME
DB_URL="${DB_URL:-postgresql://rl_user:CHANGE_ME@YOUR_CLOUD_SQL_IP:5432/researchlineage}"

SCHEMA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour helpers ────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
command -v psql >/dev/null 2>&1 || die "psql not found. Install postgresql-client first."

if [[ "$DB_URL" == *"CHANGE_ME"* || "$DB_URL" == *"YOUR_CLOUD_SQL_IP"* ]]; then
    die "DB_URL is not configured. Set the DB_URL environment variable:\n  export DB_URL='postgresql://rl_user:<password>@<host>:5432/researchlineage'"
fi

# ── Connection test ───────────────────────────────────────────────────────────
info "Testing database connection..."
psql "$DB_URL" -c "SELECT 1" >/dev/null 2>&1 \
    || die "Cannot connect to database. Check DB_URL, network access, and credentials."
info "Connection OK."

# ── Deploy files in order ─────────────────────────────────────────────────────
FILES=(
    "01_tables.sql"
    "02_indexes.sql"
    "03_audit_columns.sql"
    "04_views.sql"
)

echo ""
info "Deploying schema from: $SCHEMA_DIR"
echo "────────────────────────────────────────"

for FILE in "${FILES[@]}"; do
    FILEPATH="$SCHEMA_DIR/$FILE"
    if [[ ! -f "$FILEPATH" ]]; then
        die "File not found: $FILEPATH"
    fi

    info "Running $FILE ..."
    if psql "$DB_URL" \
        --set ON_ERROR_STOP=1 \
        --single-transaction \
        -f "$FILEPATH" 2>&1 | sed 's/^/        /'; then
        info "$FILE ✓"
    else
        die "Failed on $FILE — schema deployment aborted. No changes committed."
    fi
    echo ""
done

echo "────────────────────────────────────────"
info "Schema deployment complete."

# ── Verification ─────────────────────────────────────────────────────────────
echo ""
info "Verifying tables..."
psql "$DB_URL" -c "
SELECT table_name, pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) AS size
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type   = 'BASE TABLE'
ORDER BY table_name;
"

info "Verifying views..."
psql "$DB_URL" -c "
SELECT table_name AS view_name
FROM information_schema.views
WHERE table_schema = 'public'
ORDER BY table_name;
"

info "Verifying triggers..."
psql "$DB_URL" -c "
SELECT tgname AS trigger_name, relname AS table_name
FROM pg_trigger
JOIN pg_class ON pg_trigger.tgrelid = pg_class.oid
WHERE tgname LIKE 'trg_%'
ORDER BY relname, tgname;
"

echo ""
info "All done. Next step: run Phase 3 migration scripts."
