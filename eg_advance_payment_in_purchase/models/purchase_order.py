from odoo import models, fields, _


class PurchaseOrder(models.Model):
    _inherit = "purchase.order"

    payment_line = fields.One2many(comodel_name="account.payment", inverse_name="purchase_id")

    def action_advance_payment(self):
        return {
            "name": _("Advance Payment"),
            "view_type": "form",
            "view_mode": "form",
            "res_model": "advance.payments.wizard",
            "view_id": self.env.ref("eg_advance_payment_in_purchase.advance_payments_wizard_form_view").id,
            "type": "ir.actions.act_window",
            "target": "new"
        }
