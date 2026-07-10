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

case "$TARGET" in
    dev)
        echo ">>> Deploying $MODULE to DEV..."
        rsync -az --delete "$SRC" dev:/srv/docker/odoo/custom-addons/"$MODULE"/
        ssh dev "docker exec odoo odoo -d MOG_DEV -u $MODULE --stop-after-init --no-http"
        echo "<<< DEV deploy $MODULE done"
        ;;
    prod)
        echo ">>> Deploying $MODULE to PROD..."
        rsync -az --delete "$SRC" mog-prod:/opt/instance1/odoo17/custom-addons/"$MODULE"/
        ssh mog-prod "sudo systemctl restart instance1"
        echo "<<< PROD deploy $MODULE done"
        ;;
    *)
        echo "ERROR: target must be 'dev' or 'prod'"
        exit 1
        ;;
esac
