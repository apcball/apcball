#!/usr/bin/env bash
set -euo pipefail

# ─── Odoo Deploy Script ────────────────────────────────────
# Usage: ./deploy.sh <module>... [--dev|--prod|--kyld] [--test]
# Deploys one or more Odoo modules to the specified server.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"

# ─── Config ────────────────────────────────────────────────
DEV_HOST="root@217.216.32.33"
DEV_ADDONS="/srv/docker/odoo/custom-addons"
DEV_DB="MOG_DEV"
DEV_CMD="docker exec odoo odoo -d $DEV_DB -u %s --stop-after-init --no-http"
DEV_TEST_CMD="docker exec odoo odoo -d $DEV_DB -u %s --test-enable --stop-after-init --no-http"

PROD_HOST="mogenit@160.187.249.148"
PROD_ADDONS="/opt/instance1/odoo17/custom-addons"
PROD_CMD="sudo systemctl restart instance1"

KYLD_HOST="mogenit@119.13.29.46"
KYLD_ADDONS="/srv/docker/odoo_kyld/custom-addons"
KYLD_DB="KYLD_PROD"
KYLD_CMD="docker exec odoo odoo -d $KYLD_DB -u %s --stop-after-init --no-http"

# ─── Parse args ────────────────────────────────────────────
MODULES=()
TARGET=""
RUN_TESTS=false

for arg in "$@"; do
    case "$arg" in
        --dev)   TARGET="dev" ;;
        --prod)  TARGET="prod" ;;
        --kyld)  TARGET="kyld" ;;
        --test)  RUN_TESTS=true ;;
        --help|-h)
            echo "Usage: $0 <module>... [--dev|--prod|--kyld] [--test]"
            exit 0
            ;;
        *)
            MODULES+=("$arg")
            ;;
    esac
done

if [ ${#MODULES[@]} -eq 0 ]; then
    echo "❌ Error: specify at least one module"
    echo "Usage: $0 <module>... [--dev|--prod|--kyld] [--test]"
    exit 1
fi

if [ -z "$TARGET" ]; then
    echo "❌ Error: specify target (--dev, --prod, or --kyld)"
    exit 1
fi

if [ "$RUN_TESTS" = true ] && [ "$TARGET" != "dev" ]; then
    echo "❌ Error: --test is only supported on DEV"
    exit 1
fi

# ─── Set target vars ───────────────────────────────────────
case "$TARGET" in
    dev)
        HOST="$DEV_HOST"
        ADDONS="$DEV_ADDONS"
        UPDATE_CMD_TEMPLATE="$DEV_CMD"
        if [ "$RUN_TESTS" = true ]; then
            UPDATE_CMD_TEMPLATE="$DEV_TEST_CMD"
        fi
        NEEDS_MODULE_UPDATE=true
        ;;
    prod)
        HOST="$PROD_HOST"
        ADDONS="$PROD_ADDONS"
        NEEDS_MODULE_UPDATE=false
        ;;
    kyld)
        HOST="$KYLD_HOST"
        ADDONS="$KYLD_ADDONS"
        UPDATE_CMD_TEMPLATE="$KYLD_CMD"
        NEEDS_MODULE_UPDATE=true
        ;;
esac

# ─── Confirm ───────────────────────────────────────────────
echo "═══════════════════════════════════════════"
echo "  Target:  $(echo $TARGET | tr '[:lower:]' '[:upper:]')"
echo "  Host:    $HOST"
echo "  Modules: ${MODULES[*]}"
if [ "$RUN_TESTS" = true ]; then
    echo "  Tests:   ENABLED ⚠️  (irreversible side effects)"
fi
echo "═══════════════════════════════════════════"
echo ""
read -p "Continue? [y/N] " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled"
    exit 1
fi

# ─── Rsync modules in parallel ─────────────────────────────
echo ""
echo "📦 Syncing modules..."
PIDS=()
for mod in "${MODULES[@]}"; do
    SRC="$PROJECT_ROOT/$mod/"
    if [ ! -d "$SRC" ]; then
        echo "⚠️  Source directory not found: $SRC"
        continue
    fi
    echo "  → $mod"
    rsync -az --delete "$SRC" "$HOST:$ADDONS/$mod/" &
    PIDS+=($!)
done

FAILED=false
for pid in "${PIDS[@]}"; do
    wait "$pid" || { FAILED=true; }
done

if [ "$FAILED" = true ]; then
    echo "❌ Some rsync operations failed"
    exit 1
fi
echo "✅ Rsync complete"

# ─── Update / Restart ─────────────────────────────────────
echo ""
if [ "$NEEDS_MODULE_UPDATE" = true ]; then
    MODULES_STR=$(IFS=,; echo "${MODULES[*]}")
    UPDATE_CMD=$(printf "$UPDATE_CMD_TEMPLATE" "$MODULES_STR")
    echo "🔄 Running: ssh $HOST \"$UPDATE_CMD\""
    ssh "$HOST" "$UPDATE_CMD"
    echo "✅ Module update complete"
else
    echo "🔄 Restarting PROD service..."
    ssh "$HOST" "$PROD_CMD"
    echo "✅ Service restarted"
fi

echo ""
echo "✅ Deploy complete: ${MODULES[*]} → $(echo $TARGET | tr '[:lower:]' '[:upper:]')"
