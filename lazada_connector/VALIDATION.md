# Validation — 17.0.2.0.0 (parity with shopee_connector 17.0.2.20.0, phases 1–2)

Reference: `shopee_connector` 17.0.2.20.0 (`Downloads/desktop/shopee_connector.zip`),
the version running on the simulated server. Base: lazada_connector after the
shipping/labels work (local commit `af3da59`).

## Checks run in this environment

- Offline API/shipping/payload suite `qa/test_shipping_offline.py`: **24 passed** (HTTP mocked).
- Python: **35 files compiled**. XML: **18 files parsed**, no duplicate XML IDs;
  view field names checked against model fields; Python XML-ID references resolved.
- Manifest: **17 data files exist**; assets `static/src/**/*`.
- JS: `node --check` on both OWL files. No registry/template clash with Shopee 2.20
  (`lazada_connector.dashboard`, `lazada_many2one_subtitle`, `lazada_connector.*` templates).
- pylint-odoo: no errors besides the intentional `cr.commit()` in the fulfillment
  worker (same design as Shopee) and a false positive on an onchange.

## Not verified yet

- Odoo integration tests (`tests/`: dashboard, hardening incl. HTTP routes, mapping
  import, price push, sync, stock import/export, fulfillment, OAuth, signature):
  **written, not executed** — no Odoo/PostgreSQL here. Run on a disposable DB:

  ```bash
  odoo -d <test_db> -u lazada_connector --test-enable --test-tags /lazada_connector --stop-after-init --no-http
  ```

- Module upgrade on the simulated server next to Shopee 2.20, view rendering,
  dashboard in the browser, company rules with real users: **not verified**.
- Live Lazada calls (price push XML, batch stock push, webhooks `message_type`,
  OAuth `state` echo) are **not tested**; field names follow Lazada's docs.

## Changed / added in this phase

- Security: `security/lazada_security.xml` (Lazada User/Manager), access CSV,
  company rules (config, mapping, log, retry, shipping), manager-only secret fields.
- Models: `lazada_config` (backfill windows, unmapped count, stock location,
  price push, OAuth expiry, webhook helpers, savepointed logs), `lazada_api`
  (batch/price XML, masking, no signed URLs in errors), `lazada_product_mapping`
  (manual/refill stock, push button), `lazada_log` (redaction, SKIP LOCKED retries),
  `product_template` (price fields), `lazada_dashboard` (new), `sale_order` /
  `res_partner` (seller company, SKU ambiguity, required-fields bypass).
- Wizards: `lazada_file_import_mixin`, `lazada_order_sync`, `lazada_mapping_import`
  (new); `lazada_stock_import` uses the mixin and rejects ambiguous SKUs.
- Controllers: hardened callback and webhook.
- Views/menus: dashboard, Sync Orders, Import Mappings, mapping and config forms;
  hidden Import Stock File / Stock / Shipping Batches; unbound shipping action.
- Static: `static/src/dashboard/*`, `static/src/fields/*`.
- Tests: `test_dashboard`, `test_hardening`, `test_mapping_import`,
  `test_price_export` (new); `test_sync`, `test_stock_*`, `test_fulfillment`,
  `test_signature` updated; tests create their own products.

## Phase 2 (Thai orders and fees)

- `res_partner`: Thai address mapping from `address1`–`address5`/`post_code`,
  masked-value guard, Thai phones, delivery contact for tax-invoice buyers,
  tax identity from `tax_code`/`branch_number`/`address_billing`.
- `sale_order` / `sale_order_line`: one line per product/price, VAT-exclusive
  prices, order number as Customer Reference, trade channel, Delivery Date by
  cut-off, cancellation handling and tag, shipping/voucher lines, Finance API
  fees and net income (`lazada_net_income`, `lazada_payment_source`).
- `lazada_config`: VAT %, cut-off, shipping/voucher products, voucher prefix.
- Tests: `tests/test_orders_th.py` (new); `test_sync` adjusted. **Not executed.**
- Not verified against real Lazada payloads: address key meanings for TH, masking
  format, `created_at`/`updated_at` format, Finance API path/parameters and row
  fields (`amount`, `fee_type`, `fee_name`).

