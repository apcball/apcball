# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = "account.move"

    def action_open_wht_installment_wizard(self):
        self.ensure_one()
        if self.move_type not in ("in_invoice", "in_refund"):
            raise UserError(_("This wizard is available only on Vendor Bills/Credit Notes."))
        if self.state != "posted":
            raise UserError(_("Bill must be posted."))
        if self.payment_state in ("paid", "reversed"):
            raise UserError(_("Bill is already paid/reversed."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Installment Payment (WHT)"),
            "res_model": "wht.installment.payment.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_move_id": self.id,
                "default_partner_id": self.partner_id.id,
                "default_amount_to_clear": abs(self.amount_residual),
            },
        }
