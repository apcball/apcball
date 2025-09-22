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

    def action_debug_vat_info(self):
        """Debug action to show VAT information in this bill"""
        self.ensure_one()
        message = "=== VAT DEBUG INFO ===\n"
        message += f"Bill: {self.name}\n"
        message += f"Total amount: {self.amount_total}\n"
        message += f"Untaxed amount: {self.amount_untaxed}\n"
        message += f"Tax amount: {self.amount_tax}\n\n"
        
        message += "Lines with tax_line_id:\n"
        for line in self.line_ids.filtered('tax_line_id'):
            message += f"- {line.account_id.name}: {line.tax_line_id.name} ({line.tax_line_id.amount}%) = {line.credit - line.debit}\n"
        
        message += "\nLines with tax_ids:\n"
        for line in self.line_ids.filtered('tax_ids'):
            taxes = ", ".join([f"{t.name} ({t.amount}%)" for t in line.tax_ids])
            message += f"- {line.account_id.name}: {taxes} = {line.credit - line.debit}\n"
            
        raise UserError(message)
