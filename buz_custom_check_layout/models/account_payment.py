from odoo import models, api, fields
from bahttext import bahttext

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _compute_check_buttons_visible(self):
        for payment in self:
            payment.show_check_buttons = (
                payment.payment_method_line_id.code == 'check_printing' and
                payment.state == 'posted' and
                not payment.is_move_sent
            )

    show_check_buttons = fields.Boolean(
        compute='_compute_check_buttons_visible',
        string='Show Check Buttons'
    )

    def amount_to_text_thai(self):
        self.ensure_one()
        return bahttext(self.amount)

    def action_preview_check(self):
        """Preview the check before printing"""
        if not self.show_check_buttons:
            return False
        return self.env.ref('buz_custom_check_layout.action_print_check').report_action(self)

    def print_checks(self):
        """Print the checks"""
        if not self.show_check_buttons:
            return False
        return self.env.ref('buz_custom_check_layout.action_print_check').report_action(self)