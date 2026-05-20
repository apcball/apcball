from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    has_posted_invoices = fields.Boolean(
        compute="_compute_has_posted_invoices",
        store=False,
    )

    @api.depends("invoice_ids.state", "invoice_ids.move_type")
    def _compute_has_posted_invoices(self):
        for order in self:
            order.has_posted_invoices = any(
                inv.move_type == "out_invoice" and inv.state == "posted"
                for inv in order.invoice_ids
            )

    def action_open_credit_note_wizard(self):
        """Open the credit note wizard for this sale order."""
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Create Credit Note",
            "res_model": "sale.order.credit.note.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_sale_id": self.id,
            },
        }
