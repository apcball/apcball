from odoo import api, fields, models

class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    analytic_auto_sync = fields.Boolean(
        string="Auto Sync Analytic",
        default=True,
        help="Automatically sync analytic from first line to other lines"
    )

    def _sync_analytic_from_first_line(self):
        """
        Sync analytic distribution from the first line to other lines.
        """
        for order in self:
            if not order.analytic_auto_sync:
                continue
            
            # Allow sync in draft, sent, to approve
            if order.state not in ['draft', 'sent', 'to approve'] and not self.env.context.get('force_sync_analytic'):
                continue

            lines = order.order_line.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
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

    @api.onchange('order_line')
    def _onchange_order_line_analytic_sync(self):
        if self.analytic_auto_sync:
            self._sync_analytic_from_first_line()

    @api.model_create_multi
    def create(self, vals_list):
        orders = super().create(vals_list)
        for order in orders:
            order._sync_analytic_from_first_line()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'order_line' in vals or 'analytic_auto_sync' in vals:
            self.with_context(force_sync_analytic=True)._sync_analytic_from_first_line()
        return res

    def button_confirm(self):
        self.with_context(force_sync_analytic=True)._sync_analytic_from_first_line()
        return super().button_confirm()
