from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def action_post(self):
        res = super().action_post()
        posted = self.filtered(lambda m: m.state == "posted")
        if posted:
            sol_ids = posted.line_ids.sudo().mapped("sale_line_ids").ids
            if sol_ids:
                self.env["buz.sales.performance.result"]._recompute_for_sol(sol_ids)
        return res

    def button_cancel(self):
        res = super().button_cancel()
        cancelled = self.filtered(lambda m: m.state == "cancel")
        if cancelled:
            sol_ids = cancelled.line_ids.sudo().mapped("sale_line_ids").ids
            if sol_ids:
                self.env["buz.sales.performance.result"]._recompute_for_sol(sol_ids)
        return res

    def action_reverse(self):
        # A credit note reversal eventually posts a new out_refund; the
        # action_post hook on the refund will recompute SPE. No extra work
        # needed here - kept explicit to document the flow.
        return super().action_reverse()
