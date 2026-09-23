#!/usr/bin/env bash
set -euo pipefail
# The caller stages only the addons under test in SHOPEE_QA_ADDONS.
# Keep the project name fixed so repeated runs reuse only this QA database.
here="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
compose=(docker compose -p shopee-qa -f "$here/compose.yml")
qa_db="${SHOPEE_QA_DB:-MOG_TEST_SHOPEE}"
case "$qa_db" in
  MOG_TEST_SHOPEE|MOG_TEST_SHOPEE_FRESH|MOG_TEST_SHOPEE_UPGRADE) ;;
  *) echo "Refusing non-QA database: $qa_db" >&2; exit 2 ;;
esac
common=(-c /dev/null -d "$qa_db" --db_host=postgres --db_user=odoo
  --db_password=shopee-qa-only --addons-path=/mnt/qa-addons
  --data-dir=/var/lib/odoo --workers=0 --max-cron-threads=0
  --without-demo=all --stop-after-init --http-interface=127.0.0.1 --limit-time-real=1200)
case "${1:-test}" in
  init)
    "${compose[@]}" up -d postgres
    "${compose[@]}" run --rm odoo "${common[@]}" -i shopee_connector
    ;;
  test)
    "${compose[@]}" run --rm odoo "${common[@]}" -u shopee_connector \
      --test-enable --test-tags /shopee_connector
    ;;
  fresh)
    "${compose[@]}" up -d postgres
    "${compose[@]}" run --rm odoo "${common[@]}" -i shopee_connector \
      --test-enable --test-tags /shopee_connector
    ;;
  seed-upgrade|verify-upgrade)
    "${compose[@]}" run --rm -T -e SHOPEE_QA_UPGRADE_MODE="$1" odoo shell "${common[@]}" \
      < "$here/check_upgrade.py"
    ;;
  integration)
    "${compose[@]}" run --rm odoo "${common[@]}" -i buz_partner_required_fields,marketplace_settlement
    "${compose[@]}" run --rm odoo "${common[@]}" -u shopee_connector \
      --test-enable --test-tags /shopee_connector
    ;;
  concurrency)
    "${compose[@]}" run --rm -T odoo shell "${common[@]}" \
      < "$here/check_concurrency.py"
    ;;
  offline)
    "${compose[@]}" run --rm --entrypoint python3 odoo \
      /mnt/qa-addons/shopee_connector/qa/test_shipping_offline.py
    ;;
  stop)
    # Only this disposable project's resources; RAM-backed data is discarded.
    "${compose[@]}" down
    ;;
  *) echo "Usage: $0 {init|fresh|test|integration|seed-upgrade|verify-upgrade|concurrency|offline|stop}" >&2; exit 2 ;;
esac
