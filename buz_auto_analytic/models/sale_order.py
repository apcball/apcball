from odoo import api, fields, models

class SaleOrder(models.Model):
    _inherit = "sale.order"

    analytic_auto_sync = fields.Boolean(
        string="Auto Sync Analytic",
        default=True,
        help="Automatically sync analytic from first line to other lines"
    )

    def _sync_analytic_from_first_line(self):
        """
        Sync analytic distribution from the first line to other lines.
        Only syncs if destination line has empty analytic.
        """
        for order in self:
            if not order.analytic_auto_sync:
                continue
            
            # Avoid syncing if confirmed, unless force context is present or logic allows
            # But the prompt says "action_confirm -> final validation", implying we sync ON confirm.
            # And "Realtime (UI)" which is drafts.
            # So we check state or context.
            if order.state not in ['draft', 'sent'] and not self.env.context.get('force_sync_analytic'):
                continue

            lines = order.order_line.filtered(lambda l: l.display_type not in ('line_section', 'line_note'))
            if not lines:
                continue

            # Sort to find the first line (lowest sequence)
            # In onchange (NewId), ids might be virtual, but sequence should be correct.
            # If sequence is same, fallback to id (virtual ids are strings, real are ints, mix is tricky).
            # Usually sequence is reliable enough for UI.
            
            # Note on NewId sorting: stored lines have int ids, new lines have NewIds.
            # We trust 'sequence' mostly.
            sorted_lines = lines.sorted(key=lambda l: l.sequence)
            
            first_line = sorted_lines[0]
            master_analytic = first_line.analytic_distribution

            if not master_analytic:
                continue

            for line in sorted_lines[1:]:
                # Only overwrite if empty
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
            # Sync on create to handle API/Import
            order._sync_analytic_from_first_line()
        return orders

    def write(self, vals):
        res = super().write(vals)
        if 'order_line' in vals or 'analytic_auto_sync' in vals:
            self.with_context(force_sync_analytic=True)._sync_analytic_from_first_line()
        return res

    def action_confirm(self):
        # Final validation/sync before confirming
        self.with_context(force_sync_analytic=True)._sync_analytic_from_first_line()
        return super().action_confirm()
