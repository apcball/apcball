from odoo import api, fields, models

class EmployeePurchaseRequisition(models.Model):
    _inherit = "employee.purchase.requisition"

    analytic_auto_sync = fields.Boolean(
        string="Auto Sync Analytic",
        default=True,
        help="Automatically sync analytic from first line to other lines"
    )

    def _sync_analytic_from_first_line(self):
        """
        Sync analytic distribution from the first line to other lines.
        """
        for record in self:
            if not record.analytic_auto_sync:
                continue
            
            # Sync only in 'new_request' or if forced
            if record.state != 'new_request' and not self.env.context.get('force_sync_analytic'):
                continue

            lines = record.requisition_order_ids
            if not lines:
                continue

            # Sort by ID as sequence might not exist. New IDs (NewId) are handled by sorted logic (virtual False/0).
            # If multiple NewIds, order of creation in UI is usually preserved in recordset.
            sorted_lines = lines
            # If all are new, no IDs, use recordset order.
            
            first_line = sorted_lines[0]
            master_analytic = first_line.analytic_distribution

            if not master_analytic:
                continue

            for line in sorted_lines[1:]:
                if not line.analytic_distribution:
                    line.analytic_distribution = master_analytic

    @api.onchange('requisition_order_ids')
    def _onchange_requisition_order_ids_analytic_sync(self):
        if self.analytic_auto_sync:
            self._sync_analytic_from_first_line()

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        for rec in recs:
            rec._sync_analytic_from_first_line()
        return recs

    def write(self, vals):
        res = super().write(vals)
        if 'requisition_order_ids' in vals or 'analytic_auto_sync' in vals:
            self.with_context(force_sync_analytic=True)._sync_analytic_from_first_line()
        return res
