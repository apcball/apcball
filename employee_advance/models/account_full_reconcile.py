from odoo import models


class AccountFullReconcile(models.Model):
    _inherit = 'account.full.reconcile'

    def create(self, vals_list):
        """Odoo core sets aml.full_reconcile_id via raw SQL here (see
        account.full.reconcile._update inverse), bypassing account.move.line's
        write() override. Invalidate affected advance boxes explicitly."""
        records = super().create(vals_list)
        for line in records.reconciled_line_ids:
            if line.account_id and line.partner_id:
                self.env['account.move.line']._invalidate_advance_box_balance(
                    line.account_id, line.partner_id
                )
        return records

    def unlink(self):
        """Undo-reconcile path (remove_move_reconcile) also unlinks full
        reconciles directly, bypassing account.move.line's write()."""
        pairs = [
            (line.account_id, line.partner_id)
            for line in self.reconciled_line_ids
            if line.account_id and line.partner_id
        ]
        result = super().unlink()
        for account, partner in pairs:
            self.env['account.move.line']._invalidate_advance_box_balance(account, partner)
        return result
