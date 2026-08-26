# BUZ Account Credit Note Deferred Reconcile

## Purpose

Odoo 17 auto-reconciles a Credit Note (or Reverse-invoice) against its original Invoice as soon as it is posted, flipping the invoice to `Reversed` and the credit note to `Paid` before accounting has actually settled anything. This module defers that reconciliation to a manual step so AR/AP stays open on both documents until finance chooses to reconcile (via a manual action, Register Payment, or Bank Reconciliation).

## Root cause and override rationale

Traced in Odoo 17 core (`odoo/addons/account/models/account_move.py`):

- `account.move._post()` runs, for every posted move whose `reversed_entry_id` points to a posted move:
  ```python
  draft_reverse_moves.reversed_entry_id._reconcile_reversed_moves(draft_reverse_moves, self._context.get('move_reverse_cancel', False))
  ```
  This fires **unconditionally on the presence of the link**, not on the `cancel` flag used at creation time. This — not `_compute_payment_state` — is what silently reconciles the invoice and credit note.
- `_reconcile_reversed_moves()` groups un-reconciled receivable/payable lines from the pair and calls standard `reconcile()` on them.
- The wizard `account.move.reversal.reverse_moves()` (`account/wizard/account_move_reversal.py`) sets `cancel=True` (→ `move_reverse_cancel=True`) only for the **"Reverse and Create Invoice"** (modify) flow and for reversing a plain journal entry (`move_type == 'entry'`). A normal Credit Note / Reverse of an invoice or bill always uses `cancel=False`.

This module overrides only `account.move._reconcile_reversed_moves()`. For each `(move, reverse_move)` pair it skips calling `super()` (i.e. skips the reconcile) when:

1. `company.buz_deferred_credit_note_reconcile` is enabled, **and**
2. `move_reverse_cancel` is `False` (plain Credit Note / Reverse — not the cancel+replace flow), **and**
3. the move is an actual invoice/refund (`is_invoice(include_receipts=True)`), not a plain journal entry reversal.

`move_reverse_cancel` is the exact discriminator Odoo itself uses to distinguish "plain reversal" from "cancel + replace", so no wizard override is needed. `_compute_payment_state` is never touched — it is computed from real reconciliation state, so it self-corrects the moment we simply don't create the reconcile. `reversed_entry_id` is likewise never touched, so the Invoice ↔ Credit Note relationship is preserved.

## Configuration

Accounting > Configuration > Settings > Customer Invoices > **Deferred Credit Note Reconciliation** (checkbox). Stored on `res.company.buz_deferred_credit_note_reconcile` (default `True`), company-dependent so multi-company setups can differ. When disabled for a company, that company's reversals behave exactly like standard Odoo 17.

## Manual reconciliation

On a posted Credit Note / Vendor Refund with an original invoice, users in **Deferred Credit Note Reconciliation Manager** (`group_buz_credit_note_reconcile_manager`, implied by Accounting Manager) see a **Reconcile with Original Invoice** button. It calls standard `account.move.line.reconcile()` on the open receivable/payable lines of both documents — full or partial per the amounts involved — and posts a chatter message on both documents. It never writes `payment_state` or `amount_residual` directly.

## Known limitations

- Plain journal entry reversals (`move_type == 'entry'`) always reconcile automatically, matching standard Odoo — out of scope per the business requirement (invoices/credit notes only).
- "Reverse and Create Invoice" (cancel + replacement) keeps 100% standard Odoo behavior, since that flow depends on the reconcile to retire the original invoice correctly.

## Install

```bash
bash scripts/deploy.sh dev buz_account_credit_note_deferred_reconcile
ssh dev "docker exec odoo odoo -d MOG_DEV -i buz_account_credit_note_deferred_reconcile --stop-after-init --no-http"
```

## Upgrade

```bash
bash scripts/deploy.sh dev buz_account_credit_note_deferred_reconcile
ssh dev "docker exec odoo odoo -d MOG_DEV -u buz_account_credit_note_deferred_reconcile --stop-after-init --no-http"
```

## UAT scenarios

1. Full Customer Credit Note — invoice and credit note both stay `Not Paid`, no matched partials.
2. Partial Customer Credit Note — invoice residual unchanged, credit note residual = its own amount.
3. Existing partial payment preserved — creating a credit note afterward does not disturb the earlier payment reconciliation.
4. Manual reconcile action — both documents reconcile via the button, `payment_state` updates via standard Odoo compute.
5. Setting disabled — reversal reconciles automatically like stock Odoo 17.
6. Vendor Bill / Vendor Refund — same deferred behavior on the payable side.
7. Multi-company — Company A (enabled) defers, Company B (disabled) reconciles automatically, independently.
