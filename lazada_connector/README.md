# Lazada Connector (Odoo 17)

Sync **stock** and **orders** with the Lazada Open Platform API, and push
Odoo stock back to Lazada. Module layout and workflows mirror
`shopee_connector`.

## What it does

- **OAuth for multiple sellers**: each connection has its own credentials,
  tokens, callback state, and seller routing. The callback never stores a
  code on an arbitrary first shop.

- **Stock pull (reference only)**: available stock per SKU from Lazada ->
  shown on the product variant form (`Lazada Available Stock`). Product
  SKUs (`SellerSku`) are matched against `product.product.default_code`
  (case-insensitive when the match is unique). SKUs without an Odoo match
  are kept under **Product Mappings** with item name, variant and stock so
  they can be linked by hand.
- **Order pull**: new orders from Lazada (incremental window, with a two-day
  initial lookback) -> **draft** Sale Orders in Odoo, tagged
  `is_lazada_order`. Lines matched by `SellerSku` -> stored
  `lazada_sku_id` / `lazada_item_id` -> `LAZADA_UNMAPPED` placeholder.
- **Customer mapping**: buyers are matched per seller by Lazada buyer key
  (customer email, else name) and created as Odoo contacts with shipping
  phone and address.
- **Order status sync**: imported orders retain the raw Lazada payload and
  current status; status can be refreshed manually, by cron, or by webhook.
- **Stock push (Odoo -> Lazada)**: opt-in. When a seller connection has
  *Push Stock to Lazada* enabled, each linked variant's Odoo free-to-use
  quantity (on-hand minus reserved, in the chosen warehouse) is pushed via
  `product/price_quantity/update`. Unchanged quantities are skipped.
- **Lazada stock file import**: from **Lazada -> Import Stock File**, upload
  a CSV or (when `openpyxl` is installed) XLSX export with `SKU` plus
  `Stock`, `Quantity`, or `Available Stock`. Values are stored in the
  product's `Lazada Available Stock` field only; Odoo On Hand is not
  changed. Unknown SKUs and invalid quantities are rejected, and products
  are never created. **Export All** (same gear menu) downloads an XLSX of
  every Lazada-linked product that can be edited and re-imported as-is.
- Manual "... Now" buttons + optional cron (all sync crons disabled by
  default; token-refresh cron enabled).
- **Webhooks**: `/lazada/webhook` (also accepts `/lazada/webhook/<seller_id>`)
  validates the configured secret (or app secret when no secret is
  configured), routes by `seller_id`, and queues failed order work for
  retry.
- **API logs and retry queue**: requests, responses, webhook events, errors,
  attempts, and backoff state are visible under **Logs & Queue**.

## Install

1. Copy `lazada_connector` into the Odoo addons path.
2. `pip install requests` in the Odoo environment.
3. Restart Odoo, Apps -> Update Apps List -> install "Lazada Connector".

## Setup

1. **Lazada -> Seller Connections -> New**.
2. Fill `App Key`, `App Secret`, `Region` from the Lazada Open Platform
   (Developer) console. Set `Company` + (for push) `Stock Source Warehouse`.
3. Set `Redirect URL` to a URL under the callback domain registered on the
   Lazada app, e.g. `https://mogdev.work/lazada/callback`.
4. Optionally set a webhook secret and a marketplace fallback customer.
5. Save, click **"1. Get Authorization Link"**, authorize the seller.
6. Lazada redirects to `/lazada/callback`; the callback immediately exchanges
   the single-use code and returns to the seller connection. The seller id is
   filled from the token response or `/seller/get`.
7. Click **"Test Connection"**. If the callback reports a failure, start a
   new authorization; Lazada authorization codes expire after 30 minutes and
   cannot be reused.
8. **"Sync Stock Now"** / **"Import Orders Now"** / **"Sync Order Status"**
   test the pull path.
9. To push stock: tick **"Push Stock to Lazada"**, pick the warehouse, tick
   **"Push Stock to Lazada"** on the relevant product variants, click
   **"Push Stock Now"**.
10. To import a Lazada export file, open **Lazada -> Import Stock File** and
   use the gear menu: **Import** uploads a CSV/XLSX containing SKU and
   stock/quantity columns; **Export All** downloads the linked products as
   XLSX.
11. Enable the pull/push crons (Settings -> Technical -> Scheduled Actions)
    once manual runs are clean. Token refresh and retry processing are
    enabled by default; sync jobs are disabled by default.

## Notes

- Lazada has one central OAuth service (`https://auth.lazada.com/rest`) and
  no separate API sandbox. The connection's Environment value is retained for
  configuration compatibility; it does not change the OAuth endpoint.

- Access tokens last ~7 days; auto-refreshed from the stored
  `refresh_token` (90 days) on every sync and by the
  "Lazada: Refresh Access Tokens" cron (every 3h).
- `product/price_quantity/update` sends an XML `payload`
  (`Request/Product/Skus/Sku` with `ItemId`, `SkuId`, `SellerSku`,
  `Quantity`); if Lazada rejects the payload, adjust
  `LazadaAPI.update_stock` in `models/lazada_api.py`.
- Order import sends `created_after`/`created_before` in ISO 8601 (UTC) and
  continues each run from the end of the previous window.
- Products must exist in Odoo with `default_code` = Lazada `SellerSku` for
  stock to match; unmapped order SKUs still create the order against the
  `LAZADA_UNMAPPED` placeholder product.
- Lazada API hosts are region specific (api.lazada.co.th for Thailand);
  pick the region matching the seller's site.

## Batch shipping and labels

Select imported orders and use **Action -> Lazada: Arrange shipment and
labels**. The background worker packs each order (`/order/fulfill/pack`),
sets it ready to ship (`/order/package/rts`) and downloads the AWB PDF
(`/order/package/document/get`); labels are downloaded as original PDFs in a
ZIP with a result manifest. Pickup vs drop-off is not chosen per order: it
follows the warehouse setting in Lazada Seller Center. See
`SHIPPING_GUIDE_TH.md` for setup, limitations and test status. Odoo
installation and live Lazada calls have not been verified yet.

## 17.0.2.0.0 — parity with shopee_connector 17.0.2.20.0

- **Menus** as in the Shopee app: Dashboard, Orders, Sync Orders, Logs &
  Queue, Configurations (Seller Connections, Product Mappings, Import
  Mappings). Import Stock File, Stock and Shipping Batches are hidden
  (the code stays); the "Arrange shipment" action is unbound like Shopee.
- **Lazada Ops Dashboard** (`lazada.dashboard`, OWL client action
  `lazada_connector.dashboard`): API errors, failed retries, stock sync
  failures, unmapped listings, stale stock pushes, shipments needing
  attention, order status/trend, sync success rate, seller health and the
  Lazada scheduled actions; filter by seller and 1/7/30 days.
- **Access groups** *Lazada User* (menu, dashboard, stock wizards) and
  *Lazada Manager* (connections, credentials, order sync, mappings,
  shipping). Admin/root are managers by default; give other users a group.
  Company rules isolate connections, mappings, logs, retries and shipping.
- **Sync Orders** wizard: import orders created in a date range (one-off
  backfill, fetched in 15-day windows) or refresh order statuses.
- **Product Mappings**: Odoo warehouse stock, manual "Odoo Available Stock",
  "Refill When Lazada Stock Below", Push Odoo Stock button/action,
  Internal Reference subtitle (widget `lazada_many2one_subtitle`, distinct
  from Shopee's widget so both apps can be installed together).
  **Import Mappings** reads CSV/XLSX with `SellerSku`, `Internal Reference`
  and optional `Lazada Item ID`, `Lazada SKU ID`, `Refill...`, `Active`;
  dry run by default.
- **Stock / price push**: optional Stock Source Location; variants of one
  Lazada item go out in one `price_quantity/update` call; push again when
  Lazada's stock drifts; **Push Price to Lazada** (seller switch + per
  variant flag, cron "Lazada: Push Price" disabled by default).
- **Hardening**: OAuth state expires after 10 minutes and is consumed once
  (a callback without `state` is only accepted for a single pending
  authorization); webhooks reject non-object payloads, inconsistent seller
  ids and invalid order ids, process in a savepoint and answer 503 when the
  retry cannot be queued; retry worker uses `FOR UPDATE SKIP LOCKED`,
  validates payloads, respects backoff and inactive sellers; logs redact
  secrets (nested and serialized) and can never abort the business
  transaction; credentials are Lazada Manager fields; ambiguous SKUs are
  rejected; order import is scoped to the seller's company.

### Phase 2 — Thai orders and Lazada fees

- **Buyers**: the shipping address maps to Odoo as street = `address1`
  (repeated sub-district/district/province/zip removed), street2 =
  `address5` (ตำบล/แขวง), city = `address4` (อำเภอ/เขต), state = `address3`,
  zip = `post_code`; phones `66XXXXXXXXX` become `0XXXXXXXXX`. Masked values
  (`****`) are never written and company data is never copied onto buyers;
  masked buyers are not merged into one contact. Orders with `tax_code`
  (+ `branch_number`, `address_billing`) put the tax identity on the buyer
  and the recipient on a delivery contact. Buyers skip
  `buz_partner_required_fields` checks.
- **Orders**: Lazada's per-unit items become one line per product/price
  (cancelled units left out), unit prices exclude VAT (seller setting,
  default 7%), Customer Reference = Lazada order number, Trade Channel =
  Lazada when `marketplace_settlement` offers it, Delivery Date from the
  payment time and the seller's cut-off (default 14:00), cancelled orders
  cancel quotations or tag confirmed orders "Lazada: ยกเลิกหลัง Confirm".
  Status sync also fills the recipient once Lazada unmasks it.
- **Payment details**: shipping (Service04) and seller voucher lines from
  the order data; for shipped/delivered quotations the Finance API
  (`/finance/transaction/details/get`) adds commission/payment fees and the
  net income (`Lazada Order Income`) to the order note, like Shopee's
  escrow summary. Only quotations are changed; re-applying replaces lines.

Field names follow Lazada's documentation; verify them against real orders
(`Lazada Payload` on the order) before relying on them. "Import Buyer
Addresses" waits for a Lazada Seller Center export sample.
