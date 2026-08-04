# POS Lite Order Form — CSS Reskin

## Context
User supplied a mockup (purple, card-based info row, cart-style order lines) originally built for the pos_lite Terminal aesthetic and asked to bring the same look to the backoffice `pos.lite.order` form view. Full pixel-match would require a custom OWL/QWeb page (loses standard Odoo form features: chatter, statusbar, validation, undo). Decision: CSS-only reskin of the existing standard Odoo form — keep all fields/widgets/behavior, restyle via scoped SCSS.

## Scope
- `pos_lite/views/pos_order_view.xml` (`view_pos_lite_order_form`): minor arch changes — add a `.pos-lite-order-form` class on `<form>`, add a small partner-name pill next to the title, pull `channel`/`warehouse_id`/`date_order` into a 3-card info row.
- New `pos_lite/static/src/scss/pos_lite_order_form.scss`, all rules scoped under `.pos-lite-order-form` so no other view is affected.
- `pos_lite/__manifest__.py`: register the SCSS under `web.assets_backend`.
- No model, field, button, or business-logic changes.

## Visual changes
1. Title row: purple pill badge showing customer name next to the order name.
2. Info row: Channel / Warehouse / Date as 3 icon-cards (rounded, light-purple icon chip) above the existing Order Info / Session groups.
3. Stat buttons (Print Invoice, Picking, Returns, Exchanges): purple-outline pill styling via CSS.
4. Order lines editable list: rounded product thumbnails, row hover, tighter padding — CSS only, no qty +/- stepper widget (explicitly out of scope).
5. Totals footer (already restructured to `oe_subtotal_footer oe_right` in a prior change): soft card background, bold purple Total, red Due.

## Verification
- `bash scripts/deploy.sh dev pos_lite`, open an order in DEV, visually confirm the reskin renders correctly and no other backend views are affected (spot-check another form, e.g. Contacts, is untouched).
