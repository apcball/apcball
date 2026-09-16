#!/usr/bin/env bash
# Deploy Odoo module to DEV or PROD
# Usage: ./scripts/deploy.sh <dev|prod> <module_name>
set -euo pipefail

TARGET="${1:?Usage: deploy.sh <dev|prod> <module_name>}"
MODULE="${2:?Usage: deploy.sh <dev|prod> <module_name>}"
SRC="./${MODULE}/"

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
        ssh dev "docker exec odoo odoo -d MOG_DEV -u $MODULE --stop-after-init --no-http"
        printf "$UPDATE_LIST_PY" "MOG_DEV" "MOG_DEV" | ssh dev "docker exec -i odoo python3 -c \"\$(cat)\""
        echo "<<< DEV deploy $MODULE done"
        ;;
    prod)
        echo ">>> Deploying $MODULE to PROD..."
        rsync -az --delete "$SRC" mog-prod:/opt/instance1/odoo17/custom-addons/"$MODULE"/
        ssh mog-prod "chmod -R +r /opt/instance1/odoo17/custom-addons/$MODULE"
        printf "$UPDATE_LIST_PY" "MOG_LIVE" "MOG_LIVE" | ssh mog-prod "source /opt/instance1/odoo17-venv/bin/activate && python3 -c \"\$(cat)\""
        ssh mog-prod "sudo systemctl restart instance1"
        echo "<<< PROD deploy $MODULE done"
        ;;
    *)
        echo "ERROR: target must be 'dev' or 'prod'"
        exit 1
        ;;
esac
