# -*- coding: utf-8 -*-
################################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2024-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Anfas Faisal K (odoo@cybrosys.info)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
################################################################################
from odoo import api, fields, models


class AccountMove(models.Model):
    """This class extends the base 'purchase.order' model to introduce a new
     field, 'is_exchange',which allows users to manually apply an exchange
     rate for a transaction. When this option is enabled,users can specify
    the exchange rate through the 'rate' field."""
    _inherit = 'account.move'

    is_exchange = fields.Boolean(string='Apply Manual Exchange',
                                 help='Check this box if you want to manually '
                                      'apply an exchange rate for this '
                                      'transaction.',
                                 copy=False,
                                 states={'posted': [('readonly', True)]})
    rate = fields.Float(string='Rate', 
                        help='specify the rate',
                        readonly=False, 
                        store=True,
                        default=1.0, 
                        digits=(12, 4), 
                        copy=False,
                        states={'posted': [('readonly', True)]})


class AccountMoveLine(models.Model):
    """Extend account move line to use manual exchange rate."""
    _inherit = 'account.move.line'

    @api.depends('currency_id', 'company_id', 'move_id.date', 'move_id.is_exchange', 'move_id.rate')
    def _compute_currency_rate(self):
        """Override to use manual exchange rate when enabled."""
        for line in self:
            if line.move_id.is_exchange and line.move_id.rate and line.move_id.rate > 0:
                # Use manual rate
                line.currency_rate = line.move_id.rate
            else:
                # Use standard currency rate
                super(AccountMoveLine, line)._compute_currency_rate()
    
    @api.depends('quantity', 'discount', 'price_unit', 'tax_ids', 'currency_id', 'move_id.is_exchange', 'move_id.rate')
    def _compute_totals(self):
        """Override to apply manual exchange rate."""
        for line in self:
            if line.display_type in ('line_section', 'line_note'):
                continue
                
            # Call parent to compute standard amounts
            super(AccountMoveLine, line)._compute_totals()
            
            # Apply manual rate if enabled
            if line.move_id.is_exchange and line.move_id.rate and line.move_id.rate > 0:
                company_currency = line.company_id.currency_id
                if line.currency_id and line.currency_id != company_currency:
                    # Recalculate balance with manual rate
                    if line.price_subtotal:
                        balance = line.price_subtotal * line.move_id.rate
                        line.debit = balance if balance > 0.0 else 0.0
                        line.credit = -balance if balance < 0.0 else 0.0
                        line.balance = balance
