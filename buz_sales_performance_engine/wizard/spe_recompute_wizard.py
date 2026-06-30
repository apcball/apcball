from odoo import fields, models


class SpeRecomputeWizard(models.TransientModel):
    _name = "buz.spe.recompute.wizard"
    _description = "SPE: Recompute Performance"

    mode = fields.Selection(
        [
            ("all", "Full rebuild (all lines)"),
            ("range", "By invoice date range"),
            ("orders", "Specific sale orders"),
        ],
        string="Mode", required=True, default="range",
    )
    date_from = fields.Date(string="From", default=fields.Date.context_today)
    date_to = fields.Date(string="To", default=fields.Date.context_today)
    sale_order_ids = fields.Many2many("sale.order", string="Sale Orders")

    def action_recompute(self):
        self.ensure_one()
        Result = self.env["buz.sales.performance.result"]
        if self.mode == "all":
            Result._cron_rebuild_all()
        elif self.mode == "orders" and self.sale_order_ids:
            Result._recompute_for_orders(self.sale_order_ids.ids)
        elif self.mode == "range":
            # Recompute every SOL whose posted invoices fall in range.
            aml_sol_field = self.env["account.move.line"]._fields["sale_line_ids"]
            rel_table = aml_sol_field.relation
            rel_col_aml = aml_sol_field.column1
            rel_col_sol = aml_sol_field.column2
            self.env.cr.execute(
                """
                SELECT DISTINCT link.""" + rel_col_sol + """
                FROM """ + rel_table + """ link
                JOIN account_move_line aml ON aml.id = link.""" + rel_col_aml + """
                JOIN account_move am ON am.id = aml.move_id
                WHERE am.state = 'posted'
                  AND am.move_type IN ('out_invoice','out_refund')
                  AND am.invoice_date BETWEEN %s AND %s
                """,
                (self.date_from, self.date_to),
            )
            sol_ids = [r[0] for r in self.env.cr.fetchall()]
            if sol_ids:
                Result._recompute_for_sol(sol_ids)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": "Performance recomputed.",
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
