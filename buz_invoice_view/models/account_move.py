from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = 'account.move'

    sale_client_order_ref = fields.Char(
        string='Customer Reference',
        compute='_compute_sale_client_order_ref',
        store=True,
        help="Customer Reference from the Sale Order"
    )

    @api.depends('invoice_line_ids.sale_line_ids.order_id.client_order_ref')
    def _compute_sale_client_order_ref(self):
        for move in self:
            # Get all client_order_refs from linked sale orders
            refs = move.invoice_line_ids.sale_line_ids.order_id.mapped('client_order_ref')
            # Filter out empty references and remove duplicates
            unique_refs = list(set([ref for ref in refs if ref]))
            # Join with comma
            move.sale_client_order_ref = ", ".join(unique_refs) if unique_refs else False
