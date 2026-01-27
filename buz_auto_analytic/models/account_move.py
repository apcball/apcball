from odoo import api, fields, models

class AccountMove(models.Model):
    _inherit = "account.move"

    analytic_auto_sync = fields.Boolean(
        string="Auto Sync Analytic",
        default=True,
        help="Automatically sync analytic from first line to other lines"
    )

    def _sync_analytic_from_first_line(self):
        """
        Sync analytic distribution from the first line to other lines.
        """
        for move in self:
            if not move.analytic_auto_sync:
                continue
            
            # Skip if posted, unless forced
            if move.state == 'posted' and not self.env.context.get('force_sync_analytic'):
                continue

            # Only for Invoices/Bills, not necessarily Journal Entries (unless they use invoice_line_ids)
            # But checking invoice_line_ids covers it.
            
            lines = move.invoice_line_ids.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
            if not lines:
                continue

            sorted_lines = lines.sorted(key=lambda l: l.sequence)
            first_line = sorted_lines[0]
            master_analytic = first_line.analytic_distribution

            if not master_analytic:
                continue

            for line in sorted_lines[1:]:
                if not line.analytic_distribution:
                    line.analytic_distribution = master_analytic

    @api.onchange('invoice_line_ids')
    def _onchange_invoice_line_ids_analytic_sync(self):
        if self.analytic_auto_sync:
            self._sync_analytic_from_first_line()

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        for move in moves:
            move._sync_analytic_from_first_line()
        return moves

    def write(self, vals):
        res = super().write(vals)
        if 'invoice_line_ids' in vals or 'analytic_auto_sync' in vals:
            self.with_context(force_sync_analytic=True)._sync_analytic_from_first_line()
        return res

    def action_post(self):
        self.with_context(force_sync_analytic=True)._sync_analytic_from_first_line()
        return super().action_post()
