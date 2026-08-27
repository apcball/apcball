# Shopee Connector (Odoo 17)

Sync **stock** and **orders** with the Shopee Open Platform v2 API, and push
Odoo stock back to Shopee.

## What it does

- **Stock pull (reference only)**: remaining stock per SKU from Shopee -> shown
  on the product variant form (`Shopee Available Stock`). Supports both
  item-level SKUs and model/variant SKUs (Shopee "models"): `model_sku` /
  `item_sku` are matched against `product.product.default_code`.
- **Order pull**: new orders from Shopee (last 24h window) -> **draft** Sale
  Orders in Odoo, tagged `is_shopee_order`. Lines matched by
  `model_sku` -> `item_sku` -> stored `shopee_model_id` / `shopee_item_id` ->
  `SHOPEE_UNMAPPED` placeholder.
- **Stock push (Odoo -> Shopee)**: opt-in. When a shop connection has
  *Push Stock to Shopee* enabled, each linked variant's Odoo free-to-use
  quantity (on-hand minus reserved, in the chosen warehouse) is pushed via
  `update_stock`. Unchanged quantities are skipped.
- Manual "... Now" buttons + optional cron (all sync crons disabled by
  default; token-refresh cron enabled).

## Not included

- No order status push-back (ship / cancel).
- No webhook push events.
- Single-shop callback controller (no multi-shop routing).

## Install

1. Copy `shopee_connector` into the Odoo addons path.
2. `pip install requests` in the Odoo environment.
3. Restart Odoo, Apps -> Update Apps List -> install "Shopee Connector".

## Setup

1. **Shopee -> Shop Connections -> New**.
2. Fill `Partner ID`, `Partner Key`, `Environment` (sandbox/production) from
   the Shopee Open Platform App Detail page. Set `Company` + (for push)
   `Stock Source Warehouse`.
3. Set `Marketplace Customer` (required for order import): imported draft SOs
   are billed to this partner; the real buyer name goes to `Customer
   Reference` and the recipient address to the order notes.
4. Set `Redirect URL` to a URL under the domain registered on the Shopee app,
   e.g. `https://mogdev.work/shopee/callback`.
4. Save, click **"1. Get Authorization Link"**, authorize the shop.
5. Shopee redirects to `/shopee/callback`, which stores `code` + `shop_id`
   back on the record.
6. Click **"2. Exchange Token"**, then **"Test Connection"**.
7. **"Sync Stock Now"** / **"Sync Orders Now"** to test the pull path.
8. To push stock: tick **"Push Stock to Shopee"**, pick the warehouse, tick
   **"Push Stock to Shopee"** on the relevant product variants, click
   **"Push Stock Now"**.
9. Enable the `ir.cron` jobs (Settings -> Technical -> Scheduled Actions:
   "Shopee: Sync Stock" / "Sync Orders" / "Push Stock") once manual runs are
   clean.

## Notes

- Access tokens last 4h; auto-refreshed from the stored `refresh_token`
  (30 days) on every sync and by the "Shopee: Refresh Access Tokens" cron
  (every 3h).
- `update_stock` sends `seller_stock`; if the Shopee sandbox rejects the
  payload, adjust `ShopeeAPI.update_stock` in `models/shopee_api.py`.
- Products must exist in Odoo with `default_code` = Shopee item/model SKU for
  stock to match; unmapped order SKUs still create the order against the
  `SHOPEE_UNMAPPED` placeholder product.
