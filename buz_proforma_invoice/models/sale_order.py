from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def action_print_proforma_invoice(self):
        self.ensure_one()
        return self.env.ref('buz_proforma_invoice.action_report_proforma_invoice').report_action(self)