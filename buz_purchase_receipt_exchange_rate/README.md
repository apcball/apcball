# Purchase Receipt Exchange Rate

Sets a per-Receipt Exchange Rate Date/Exchange Rate for foreign-currency
Purchase Order receipts, and makes Stock Valuation + its Accounting Entry
use that rate.

## How it works

- Only affects `stock.picking` of type incoming with moves linked to a
  Purchase Order whose currency differs from the company currency.
- `Get Exchange Rate` looks up `res.currency.rate` at the chosen date (falls
  back to the latest earlier rate, like Odoo core does, and reports the
  actual date used).
- `Recalculate Cost` only previews the expected cost — it does not create
  any `stock.valuation.layer`.
- On Validate, `custom_cost_price` (from `biz_receipt_transfer_cost`) is set
  to the exchange-rate-adjusted unit cost before the standard valuation flow
  runs, so the SVL created by `biz_receipt_transfer_cost` uses this value.
- The Purchase Order line price is never modified. The global
  `res.currency.rate` is never modified.

## Known limitations (by design)

- Only PO-linked incoming receipts are affected — not dropship, internal
  transfers, manufacturing, or non-PO receipts.
- The invoice-adjustment branch in core `_get_price_unit()` (used when
  `qty_invoiced > qty_received`) is bypassed for eligible moves: the manual
  rate always applies to the PO's gross price unit.
- If a Vendor Bill for the same PO line posts later at a different implied
  rate, Odoo's own price-difference SVL logic still runs unmodified — this
  module does not attempt to reconcile the receipt rate with the bill rate.
- Standard-cost products are unaffected **by this module**: the gate
  (`_use_receipt_exchange_rate`) explicitly excludes `cost_method ==
  'standard'`, mirroring Odoo core (`stock_account` only calls
  `_get_price_unit()` for AVCO/FIFO). Note that `biz_receipt_transfer_cost`
  already forces `use_custom_cost` on every incoming move regardless of
  cost method (pre-existing behavior, unrelated to this module) - so a
  standard-cost product's receipt valuation may still differ from
  `product.standard_price` on this database, just never because of the
  exchange rate set here.
- Historical Receipts validated before this module was installed are not
  migrated or recomputed.
