# -*- coding: utf-8 -*-
###############################################################################
#
#   Cybrosys Technologies Pvt. Ltd.
#
#   Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#   Author: Remya R( odoo@cybrosys.com )
#
#   You can modify it under the terms of the GNU AFFERO
#   GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#   You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#   (AGPL v3) along with this program.
#   If not, see <http://www.gnu.org/licenses/>.
#
###############################################################################
from odoo import models


class AccountPayment(models.Model):
    """
    This class inherits from the 'account.payment' model to add specific
    features and behavior related to printing checks and handling payment
    information. It overrides the 'print_checks' method to provide a custom
    wizard view for selecting and formatting cheque printing options.
    """
    _inherit = 'account.payment'

    def print_checks(self):
        """
        Overriding print_checks button to generate a wizard view to print
        cheque by selecting a cheque print format.
        """
        # Default to using the payment date
        cheque_date = self.date
        
        # If the payment method is specifically 'Checks', use the payment date
        if self.payment_method_line_id.payment_method_id.name == 'Checks':
            cheque_date = self.date
        # If the payment method is 'PDC' and effective_date exists, use that
        elif hasattr(self, 'effective_date') and self.payment_method_line_id.payment_method_id.name == 'PDC':
            cheque_date = self.effective_date
            
        return {
            'name': "Cheque Format",
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'cheque.types',
            'target': 'new',
            'context': {
                'default_partner_id': self.partner_id.id,
                'default_cheque_amount_in_words': self.check_amount_in_words,
                'default_cheque_date': cheque_date,
                'default_cheque_amount': self.amount,
                'default_check_number': self.check_number,
                'default_payment_id': self.id
            }
        }
        
    def action_unmark_sent(self):
        """Unmark the payment as sent."""
        self.write({'is_move_sent': False})
        
    def action_void_check(self):
        """Mark the payment as void and reset its state."""
        self.write({'is_move_sent': False})
        self.action_draft()
