# Lazada Connector (Odoo 17)

Sync **stock** and **orders** with the Lazada Open Platform API, and push
Odoo stock back to Lazada. Module layout and workflows mirror
`shopee_connector`.

## What it does

- **OAuth for multiple sellers**: each connection has its own credentials,
  tokens, callback state, and seller routing. The callback never stores a
  code on an arbitrary first shop.

- **Stock pull (reference only)**: remaining stock per SKU from Lazada ->
  shown on the product variant form (`Lazada Available Stock`). Product
  SKUs (`SellerSku`) are matched against `product.product.default_code`.
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
- `product/price_quantity/update` sends a `payload` JSON list; if Lazada
  rejects the payload, adjust `LazadaAPI.update_stock` in
  `models/lazada_api.py`.
- Products must exist in Odoo with `default_code` = Lazada `SellerSku` for
  stock to match; unmapped order SKUs still create the order against the
  `LAZADA_UNMAPPED` placeholder product.
- Lazada API hosts are region specific (api.lazada.co.th for Thailand);
  pick the region matching the seller's site.
