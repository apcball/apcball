# QA and bugfix — 2026-09-23

Base version: `17.0.2.18.0`, unchanged. Existing uncommitted development was
retained. No commit, push or deployment to the operational DEV/PROD instance was
performed. All test writes target disposable QA databases.

## Fixes

- OAuth callbacks require a matching, unexpired state and shop. State expires
  after ten minutes, travels in the redirect URL, and is consumed under a row
  lock. After upgrading, restart any pending authorization flow from the old code.
- Webhooks reject absent/invalid signatures, non-object JSON, inconsistent shop
  identifiers and malformed order identifiers. Processing uses a savepoint so
  database errors cannot poison the recovery transaction. `queued: true` is
  returned only after recording a retry; failed enqueue returns HTTP 503. Stock
  events now have a retry operation as well.
- Company rules protect configurations, mappings, logs and retries. Mapping,
  order and configured service-product relations check company consistency.
  Orders/new buyers use the shop's company; stock operations use its context.
  Credentials have Sales Manager field restrictions and form masking. Logs
  redact nested/serialized credentials; network errors no longer print signed
  URLs. Failed log insertion cannot leave the business transaction aborted.
- Retry workers use `FOR UPDATE SKIP LOCKED`, respect backoff/attempt limits,
  skip inactive shops/completed jobs, reject malformed payloads and roll back
  partial work before recording failure. Missing products/orders are not falsely
  marked successful. Fulfillment also excludes archived shops.
- Explicit status sync now filters order numbers before applying limits, fixing
  skipped orders older than the latest 200. Missing API details, invalid/repeated
  pagination cursors and exhausted page limits stop sync without advancing its
  watermark. Import-by-number verifies the returned order number.
- Zero discounted prices remain zero. Ambiguous product SKUs are rejected during
  file/order import instead of selecting the first product; explicit shop
  mappings still resolve order ambiguity.
- Tests create their own products instead of relying on live data. Partner
  validation fixtures are isolated from the regression proving that masked
  Shopee buyers work without disabling validation for ordinary contacts.

## Validation evidence

Odoo 17/PostgreSQL 16 ran on DEV in the separate Compose project `shopee-qa`.
Staging and PostgreSQL storage are RAM-backed: DEV's root disk had only about
454 MB free. The network is internal, publishes no ports and cannot reach Shopee.
Cron is disabled. Memory caps: PostgreSQL 1 GB; each Odoo runner 1.2 GB.

| Check | Result |
| --- | --- |
| Integration with `buz_partner_required_fields` and `marketplace_settlement` | 85 tests; 0 failures/errors/skips; final backoff test awaiting rerun |
| Offline API/shipping suite | 22 passed, HTTP mocked |
| Independent PostgreSQL connections | Retry lock excludes competing worker; completed retry is not replayed |
| Shipment timeout across real commits/rollback | Intent survives rollback; shipment is not resent |
| Fulfillment advisory lock | Survives intent commit |
| Fresh installation and tests | In progress |
| Original-source upgrade with committed synthetic fixtures | In progress |
| Static checks | 37 Python files parse; 14 XML files parse; all 14 manifest paths exist |

Counts use `odoo.tests.result`, not the larger internal `odoo.tests.stats`
counter. Coverage includes auth, company isolation, PostgreSQL failure recovery,
pagination, older orders, SKU ambiguity, stock partial failures, Thai/masked
addresses, payment details, label states and partial ZIP export. Views are checked
through Odoo's view API; this is not a browser visual inspection.

The original baseline skipped 42 of 53 tests because product fixtures/openpyxl
were missing. These skips are not counted as passes. The integration suite now
supplies both dependencies.

## Reproduce

Use `qa/compose.yml`, separate from the root compose file used by `pos_lite`.
Export `SHOPEE_QA_ADDONS` pointing to an isolated copy of this addon and, for
integration checks, `buz_partner_required_fields`, `l10n_th_partner`,
`partner_company_type`, `partner_firstname`, and `marketplace_settlement`.
Export `SHOPEE_QA_PYTHON` pointing to compatible `openpyxl`/`et_xmlfile` packages,
or an empty directory when the image already contains them. The image must have
`requests`. `SHOPEE_QA_IMAGE` defaults to existing image `odoo_kyld:17`; no image
is pulled.

```bash
bash shopee_connector/qa/run.sh init
bash shopee_connector/qa/run.sh integration
bash shopee_connector/qa/run.sh concurrency
bash shopee_connector/qa/run.sh offline
SHOPEE_QA_DB=MOG_TEST_SHOPEE_FRESH bash shopee_connector/qa/run.sh fresh
```

For upgrade verification set `SHOPEE_QA_DB=MOG_TEST_SHOPEE_UPGRADE`. Point the
addons variable at the original source and run `init` then `seed-upgrade` using
the new runner. Switch to patched addons, run `test` then `verify-upgrade`.
Checks preserve config, mapping, stock, retry attempts/state and logs, including
backfilled company fields. No operational database copy/customer data is used.

`bash shopee_connector/qa/run.sh stop` removes only the QA project and discards
its RAM-backed test databases. Collect evidence first. Concurrency checks remove
their own synthetic records.

## Limits and release checks

- No live Shopee calls, OAuth round trips or real carrier PDFs were tested.
  The [official push documentation](https://open.shopee.com/push-mechanism/1)
  returned HTTP 403. The existing body-HMAC formula was preserved and is **not
  certified against the current Shopee callback contract**. Verify exact signed
  bytes/headers with an official Sandbox callback before enabling webhooks.
  DEV had no webhook samples. Numeric event mapping remains unimplemented;
  unknown events are ignored. Existing order polling remains available.
- Legacy logs without a shop are restricted to administrators by the new rules.
  Historical logs and existing shared buyer contacts were not rewritten.
- Periodic status sync still covers the latest 200 orders. The fix makes
  explicitly requested older orders reachable; full historical reconciliation
  remains a separate feature.
- Split-package fulfillment is still rejected. Browser interactions and real
  printers need UAT. No operational cron or settings were changed.
- A later operational rollout must use `scripts/deploy.sh dev shopee_connector`,
  pass DEV smoke tests, then deploy PROD. Version changes, commit and push require
  the repository's explicit confirmations.

## Next development priorities

1. Verify current official webhook signing/numeric events using Sandbox fixtures.
2. Sync-health page: last success, unmapped listings and failed/pending retries,
   scoped to company/shop.
3. Date-range order/stock reconciliation with a preview before applying changes.
4. Package-level fulfillment/tracking/labels for split-package orders.

## Historical validation — 17.0.2.2.0

The original notes below are retained for history; they do not describe the
current test results or the scope of the 2026-09-23 bugfix.

- Offline API adapter and shipping-validation tests: **22 passed** (mocked HTTP, no live requests).
- Python syntax: **24 files compiled** without writing bytecode into the package.
- XML: **12 files parsed**, no duplicate XML IDs found; new view field names checked against new model fields.
- Manifest: **12 referenced files exist**.
- Odoo integration tests: **7 added, not executed**; Odoo/PostgreSQL runtime unavailable.
- Odoo installation, registry loading, view rendering, worker transactions/locking and company permissions: **not verified at runtime**.
- Shopee Sandbox/production and real carrier label printing: **not tested**. Current official API pages could not be read (403). Validate the API contract and app permissions in Sandbox before production.
- Original importer, stock logic and pre-existing security weaknesses are outside this change.

## Changed files

- `README.md`
- `__manifest__.py`
- `models/__init__.py`
- `models/shopee_api.py`
- `security/ir.model.access.csv`
- `tests/__init__.py`

## Added files

- `SHIPPING_GUIDE_TH.md`
- `data/shopee_fulfillment_cron.xml`
- `models/shopee_fulfillment.py`
- `models/shopee_shipping_helpers.py`
- `qa/test_shipping_offline.py`
- `security/shopee_fulfillment_rules.xml`
- `tests/test_fulfillment.py`
- `views/shopee_fulfillment_views.xml`
