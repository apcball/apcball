# Shopee Connector (Odoo 17)

Sync **stock** and **orders** with the Shopee Open Platform v2 API, and push
Odoo stock back to Shopee.

## What it does

- **OAuth for multiple shops**: each connection has its own credentials,
  tokens, callback state, and shop routing. The callback never stores a code
  on an arbitrary first shop.

- **Stock pull (reference only)**: remaining stock per SKU from Shopee -> shown
  on the product variant form (`Shopee Available Stock`). Supports both
  item-level SKUs and model/variant SKUs (Shopee "models"): `model_sku` /
  `item_sku` are matched against `product.product.default_code`.
- **Order pull**: new orders from Shopee (incremental window, with a two-day
  initial lookback) -> **draft** Sale Orders in Odoo, tagged
  `is_shopee_order`. Lines matched by
  `model_sku` -> `item_sku` -> stored `shopee_model_id` / `shopee_item_id` ->
  `SHOPEE_UNMAPPED` placeholder.
- **Customer mapping**: buyers are matched per shop by Shopee buyer ID and
  created as Odoo contacts with recipient phone and address.
- **Order status sync**: imported orders retain the raw Shopee payload and
  current status; status can be refreshed manually, by cron, or by webhook.
- **Stock push (Odoo -> Shopee)**: opt-in. When a shop connection has
  *Push Stock to Shopee* enabled, each linked variant's Odoo free-to-use
  quantity (on-hand minus reserved, in the chosen warehouse) is pushed via
  `update_stock`. Unchanged quantities are skipped.
- **Shopee stock file import**: the **Shopee -> Import Stock File** page lists
  products by SKU. From the gear menu, **Import** opens the upload popup for a
  CSV or (when `openpyxl` is installed) XLSX export with `SKU` plus `Stock`,
  `Quantity`, or `Available Stock`. Values are stored in the product's
  `Shopee Available Stock` field only; Odoo On Hand is not changed. Unknown
  SKUs and invalid quantities are rejected, and products are never created.
  **Export All** (same gear menu) downloads an XLSX of every Shopee-linked
  product that can be edited and re-imported as-is.
- Manual "... Now" buttons + optional cron (all sync crons disabled by
  default; token-refresh cron enabled).
- **Webhooks**: `/shopee/webhook` (also accepts `/shopee/webhook/<shop_id>`)
  validates the configured secret (or partner key when no secret is
  configured), routes by `shop_id`, and queues failed order work for retry.
- **API logs and retry queue**: requests, responses, webhook events, errors,
  attempts, and backoff state are visible under **Logs & Queue**.

## Install

1. Copy `shopee_connector` into the Odoo addons path.
2. `pip install requests` in the Odoo environment.
3. Restart Odoo, Apps -> Update Apps List -> install "Shopee Connector".

## Setup

1. **Shopee -> Shop Connections -> New**.
2. Fill `Partner ID`, `Partner Key`, `Environment` (sandbox/production) from
   the Shopee Open Platform App Detail page. Set `Company` + (for push)
   `Stock Source Warehouse`.
3. Set `Redirect URL` to a URL under the domain registered on the Shopee app,
   e.g. `https://mogdev.work/shopee/callback`.
4. Optionally set a webhook secret and a marketplace fallback customer.
5. Save, click **"1. Get Authorization Link"**, authorize the shop.
6. Shopee redirects to `/shopee/callback`; the state parameter routes the code
   back to the correct shop.
7. Click **"2. Exchange Token"**, then **"Test Connection"**.
8. **"Sync Stock Now"** / **"Import Orders Now"** / **"Sync Order Status"**
   test the pull path.
9. To push stock: tick **"Push Stock to Shopee"**, pick the warehouse, tick
   **"Push Stock to Shopee"** on the relevant product variants, click
   **"Push Stock Now"**.
10. To import a Shopee export file, open **Shopee -> Import Stock File** and
   use the gear menu: **Import** uploads a CSV/XLSX containing SKU and
   stock/quantity columns; **Export All** downloads the linked products as
   XLSX.
11. Enable the pull/push crons (Settings -> Technical -> Scheduled Actions)
   once manual runs are clean. Token refresh and retry processing are enabled
   by default; sync jobs are disabled by default.

## Notes

- Access tokens last 4h; auto-refreshed from the stored `refresh_token`
  (30 days) on every sync and by the "Shopee: Refresh Access Tokens" cron
  (every 3h).
- `update_stock` sends `seller_stock`; if the Shopee sandbox rejects the
  payload, adjust `ShopeeAPI.update_stock` in `models/shopee_api.py`.
- Products must exist in Odoo with `default_code` = Shopee item/model SKU for
  stock to match; unmapped order SKUs still create the order against the
  `SHOPEE_UNMAPPED` placeholder product.

## Batch shipping and labels (17.0.2.2.0)

Select imported orders and use **Action -> Shopee: Arrange shipment and labels**.
Carrier options must be selected before queueing; labels are downloaded as original PDFs in a ZIP with a result manifest. See `SHIPPING_GUIDE_TH.md` for setup, limitations and test status. This release is a staging candidate: Odoo installation and live Shopee integration have not been verified.
