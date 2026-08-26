from odoo import _, api, fields, models
from odoo.exceptions import UserError

RECEIVABLE_PAYABLE_TYPES = ("asset_receivable", "liability_payable")


class AccountMove(models.Model):
    _inherit = "account.move"

    buz_show_manual_reconcile = fields.Boolean(
        compute="_compute_buz_show_manual_reconcile",
    )

    @api.depends(
        "move_type",
        "state",
        "reversed_entry_id",
        "reversed_entry_id.state",
        "amount_residual",
        "reversed_entry_id.amount_residual",
    )
    def _compute_buz_show_manual_reconcile(self):
        for move in self:
            original = move.reversed_entry_id
            move.buz_show_manual_reconcile = bool(
                move.move_type in ("out_refund", "in_refund")
                and move.state == "posted"
                and original
                and original.state == "posted"
                and not move.currency_id.is_zero(move.amount_residual)
                and not original.currency_id.is_zero(original.amount_residual)
            )

    def _reconcile_reversed_moves(self, reverse_moves, move_reverse_cancel):
        """Skip Odoo's automatic reconcile between an invoice and its
        reversal for plain Credit Note / Reverse operations, so accounting
        can reconcile manually later.

        Odoo calls this unconditionally from `_post()` for every posted move
        whose `reversed_entry_id` is a posted move, regardless of `cancel`.
        `move_reverse_cancel` is the flag the "Reverse and Create Invoice"
        (cancel + replace) flow relies on to retire the original move
        correctly, so that flow (and plain journal entry reversals, which
        are out of scope) always goes through standard `super()` behavior.
        """
        to_process = self.env["account.move"]
        to_process_reverse = self.env["account.move"]
        for move, reverse_move in zip(self, reverse_moves):
            if (
                not move_reverse_cancel
                and move.company_id.buz_deferred_credit_note_reconcile
                and move.is_invoice(include_receipts=True)
            ):
                continue
            to_process += move
            to_process_reverse += reverse_move
        if to_process:
            return super(AccountMove, to_process)._reconcile_reversed_moves(
                to_process_reverse, move_reverse_cancel
            )
        return reverse_moves

    def action_reconcile_with_original_invoice(self):
        self.ensure_one()
        original = self.reversed_entry_id
        if not original:
            raise UserError(_("This document has no original invoice to reconcile with."))
        if self.state != "posted" or original.state != "posted":
            raise UserError(_("Both the credit note and the original invoice must be posted."))
        if self.commercial_partner_id != original.commercial_partner_id:
            raise UserError(_(
                "The credit note cannot be reconciled with the original invoice "
                "because they do not belong to the same partner."
            ))
        if self.company_id != original.company_id:
            raise UserError(_(
                "The credit note cannot be reconciled with the original invoice "
                "because they do not belong to the same company."
            ))

        lines = (self.line_ids + original.line_ids).filtered(
            lambda l: not l.reconciled and l.account_id.account_type in RECEIVABLE_PAYABLE_TYPES
        )
        if not lines:
            raise UserError(_(
                "There are no open receivable/payable lines to reconcile on "
                "the credit note and the original invoice."
            ))
        if len(lines.account_id) > 1:
            raise UserError(_(
                "The credit note cannot be reconciled with the original invoice "
                "because they do not share the same receivable/payable account."
            ))

        lines.reconcile()

        self.message_post(body=_(
            "Credit Note manually reconciled with original Invoice %s by %s.",
            original.name, self.env.user.name,
        ))
        original.message_post(body=_(
            "Invoice manually reconciled with Credit Note %s by %s.",
            self.name, self.env.user.name,
        ))
