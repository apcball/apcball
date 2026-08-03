# pos_lite terminal: editable unit price per cart line

## Context
Cashiers using the POS Lite terminal (`pos_lite/views/pos_lite_terminal.xml`) can currently
adjust quantity and a per-line discount, but the unit price is fixed to `product.list_price`
at add-to-cart time. Some scenarios (walk-in negotiation, custom service pricing) need the
cashier to override the unit price directly, not just apply a discount.

## Approach
Add a price input next to the existing discount input on each cart line (both stay, per
user decision), backed by a new `setPrice(productId, val)` handler mirroring `setDiscount`.

- **Frontend only.** `pos_lite/models/pos_order.py` order-line creation already accepts a
  client-supplied `price_unit` (see `_ORDER_LINE_FIELDS` in `pos_lite/controllers/main.py`,
  and `addOrder`'s line payload at `pos_lite_terminal.xml:1723` already sends
  `price_unit: l.price`). No backend or controller change needed — `l.price` just needs to
  become editable instead of fixed at add-time.
- **State:** `l.price` on the cart line object (`state.orderLines[i].price`) becomes mutable.
- **UI:** in `renderOrder()` (`pos_lite_terminal.xml:1628-1647`), add a price `<input
  type="number" min="0" step="0.01">` in `.pos-order-line-controls`, alongside the existing
  `.pos-line-disc` input. Prefill with `l.price`.
- **Handler:** new `setPrice(id, val)` function (mirrors `setDiscount`, `pos_lite_terminal.xml:1584-1599`):
  - parse float, clamp to `>= 0` (user decision: guard against negative price only, no
    cost-floor check)
  - if discount currently exceeds the new price, clamp discount down to the new price
    (existing `setDiscount` already does the reverse clamp; keep both consistent)
  - update `line.price`, then `renderOrder(); updateTotals(); renderProducts();` (same
    pattern as `setQty`/`setDiscount`)
- **Totals:** no change needed — `lineTotal()` (`pos_lite_terminal.xml:1616-1618`) already
  reads `l.price`, so editing it flows through subtotal/tax/total automatically.

## Out of scope
- No permission/role gating on who can edit price (matches existing discount input, which
  has no gating today).
- No audit log / reason-for-override field.
- No backend validation beyond what already exists (order confirm doesn't re-check
  price_unit against list price).

## Verification
- Open POS Lite terminal in DEV, add a product to cart, edit the new price field, confirm
  the line total and cart subtotal/tax/total update live.
- Set price below 0 → confirm it clamps to 0.
- Set price below current discount → confirm discount clamps down to match.
- Confirm an order with an edited price and check the resulting `pos.lite.order.line`
  `price_unit` in Odoo matches the edited value.
