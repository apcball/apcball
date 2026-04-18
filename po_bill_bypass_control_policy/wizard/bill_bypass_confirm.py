from odoo import api, fields, models

class BillBypassConfirmWizard(models.TransientModel):
    _name = 'bill.bypass.confirm.wizard'
    _description = 'Confirm Bill Bypass'

    purchase_order_id = fields.Many2one('purchase.order', string="Purchase Order", required=True)

    def action_confirm(self):
        self.ensure_one()
        return self.purchase_order_id.with_context(bypass_bill_confirm_wizard=True).action_create_invoice()
