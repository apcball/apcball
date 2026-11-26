#!/usr/bin/env bash
# Deploy Odoo module to DEV, UAT or PROD
# Usage: ./scripts/deploy.sh <dev|uat|prod> <module_name> [--upgrade]
set -euo pipefail

TARGET="${1:?Usage: deploy.sh <dev|uat|prod> <module_name>}"
MODULE="${2:?Usage: deploy.sh <dev|uat|prod> <module_name>}"
SRC="./${MODULE}/"
UPGRADE="${3:-}"

if [[ ! "$MODULE" =~ ^[a-z][a-z0-9_]*$ ]] || [[ -n "$UPGRADE" && "$UPGRADE" != "--upgrade" ]]; then
    echo "ERROR: expected a module name and optional --upgrade"
    exit 1
fi

if [ ! -d "$SRC" ]; then
    echo "ERROR: Module dir $SRC not found"
    exit 1
fi

# Refreshes ir.module.module (icon/summary/category/...) from the manifest.
# `-u <module>` upgrades code/data but does NOT re-sync this metadata — only
# update_list() diffs terp vs DB row. Without this, manifest edits (e.g. icon)
# stay stale after deploy.
UPDATE_LIST_PY='
import odoo
odoo.tools.config.parse_config(["-d", "%s", "--no-http"])
from odoo.modules.registry import Registry
reg = Registry.new("%s")
with reg.cursor() as cr:
    env = odoo.api.Environment(cr, odoo.SUPERUSER_ID, {})
    env["ir.module.module"].update_list()
    cr.commit()
'

case "$TARGET" in
    dev)
        echo ">>> Deploying $MODULE to DEV..."
        rsync -az --delete "$SRC" dev:/srv/docker/odoo/custom-addons/"$MODULE"/
        ssh dev "chmod -R +r /srv/docker/odoo/custom-addons/$MODULE"
        ssh dev "docker exec odoo odoo -d MOG_DEV -u $MODULE --stop-after-init --no-http"
        printf "$UPDATE_LIST_PY" "MOG_DEV" "MOG_DEV" | ssh dev "docker exec -i odoo python3 -c \"\$(cat)\""
        # The upgrade runs in a separate process; HTTP workers still have the
        # previous Python classes imported until the container restarts.
        ssh dev "docker restart odoo"
        echo "<<< DEV deploy $MODULE done"
        ;;
    uat)
        # Docker stack on the production host (port 8070). Always upgrades;
        # --upgrade is accepted but not needed.
        echo ">>> Deploying $MODULE to UAT..."
        UAT_DIR=/srv/docker/odoo_mogen
        rsync -az --delete --exclude='__pycache__' "$SRC" mog-prod:"$UAT_DIR/custom-addons/$MODULE"/
        ssh mog-prod "chmod -R a+rX $UAT_DIR/custom-addons/$MODULE"
        # Every docker command reads /dev/null so it cannot consume this script.
        ssh mog-prod bash -s -- "$MODULE" "$UAT_DIR" <<'UAT_SCRIPT'
set -euo pipefail
module="$1"
cd "$2"
sql() {
    docker exec postgres sh -c 'psql -U "$POSTGRES_USER" -d MOG_LIVE -v ON_ERROR_STOP=1 -Atc "$0"' "$1" < /dev/null
}
# UAT is a neutralized copy of production: crons that the upgrade switches on
# must be switched off again before the server starts. Crons that testers had
# already enabled stay enabled.
active_before="$(sql "select coalesce(string_agg(id::text, ','), '0') from ir_cron where active")"
restore() {
    sql "update ir_cron set active = false where active and id not in ($active_before)"
    docker start odoo < /dev/null
}
docker stop odoo < /dev/null
trap restore EXIT
docker compose run --rm --no-deps -T odoo odoo -c /etc/odoo/odoo.conf -d MOG_LIVE \
    -u "$module" --stop-after-init --no-http --workers=0 --max-cron-threads=0 < /dev/null
UAT_SCRIPT
        printf "$UPDATE_LIST_PY" "MOG_LIVE" "MOG_LIVE" | ssh mog-prod "docker exec -i odoo python3 -c \"\$(cat)\""
        echo "<<< UAT deploy $MODULE done"
        ;;
    prod)
        echo ">>> Deploying $MODULE to PROD..."
        rsync -az --delete "$SRC" mog-prod:/opt/instance1/odoo17/custom-addons/"$MODULE"/
        ssh mog-prod "chmod -R +r /opt/instance1/odoo17/custom-addons/$MODULE"
        if [[ "$UPGRADE" == "--upgrade" ]]; then
            # Schema changes must run with HTTP workers stopped. Run as the
            # service user so generated files keep the correct ownership.
            ssh mog-prod bash -s -- "$MODULE" <<'UPGRADE_SCRIPT'
set -euo pipefail
module="$1"
service_user="$(systemctl show instance1 --property=User --value)"
test -n "$service_user"
sudo systemctl stop instance1
trap 'sudo systemctl start instance1' EXIT
sudo -u "$service_user" /opt/instance1/odoo17-venv/bin/python3 \
    /opt/instance1/odoo17/odoo-bin -c /etc/instance1.conf -d MOG_LIVE \
    -u "$module" --stop-after-init --no-http --workers=0 --max-cron-threads=0
UPGRADE_SCRIPT
        fi
        printf "$UPDATE_LIST_PY" "MOG_LIVE" "MOG_LIVE" | ssh mog-prod "cd /opt/instance1/odoo17 && source /opt/instance1/odoo17-venv/bin/activate && ODOO_RC=/etc/instance1.conf python3 -c \"\$(cat)\""
        ssh mog-prod "sudo systemctl restart instance1"
        echo "<<< PROD deploy $MODULE done"
        ;;
    *)
        echo "ERROR: target must be 'dev', 'uat' or 'prod'"
        exit 1
        ;;
esac
