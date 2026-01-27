# -*- coding: utf-8 -*-
from odoo import models, api, _
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_print_commercial_invoice(self):
        self.ensure_one()
        # Find related invoice
        invoice = None
        if self.sale_id:
            invoices = self.sale_id.invoice_ids.filtered(lambda i: i.move_type == 'out_invoice' and i.state == 'posted')
            if invoices:
                invoice = invoices[0]  # Take the first one
        if not invoice:
            raise UserError(_("No related posted invoice found for this delivery."))
        # Return the report action for the invoice
        return self.env.ref('buz_commercial_invoice.action_report_commercial_invoice').report_action(invoice)