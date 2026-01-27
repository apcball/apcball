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


class PurchaseOrder(models.Model):
    """This class extends the base 'purchase.order' model to introduce a
    new field, 'is_exchange',which allows users to manually apply an exchange
    rate for a transaction. When this option is enabled, users can specify
    the exchange rate through the 'rate' field."""
    _inherit = 'purchase.order'

    is_exchange = fields.Boolean(string='Apply Manual Currency',
                                 help='Check this box if you want to manually'
                                      'apply an exchange rate for this '
                                      'transaction.')
    rate = fields.Float(string='Rate', help='specify the rate', compute='_compute_rate', readonly=False, store=True,
                        default=1, digits=(12, 4))

    @api.depends('is_exchange')
    def _compute_rate(self):
        """Compute the default rate value."""
        for rec in self:
            if not rec.rate:
                rec.rate = 1.0

    @api.onchange('is_exchange', 'rate')
    def _onchange_manual_currency_rate(self):
        """Recompute amounts when manual rate changes."""
        if self.is_exchange and self.rate:
            for line in self.order_line:
                if not line.display_type:
                    line._compute_amount()


class PurchaseOrderLine(models.Model):
    """Extend purchase order line to use manual exchange rate."""
    _inherit = 'purchase.order.line'

    def _convert_to_tax_base_line_dict(self):
        """Override to apply manual exchange rate."""
        self.ensure_one()
        res = super()._convert_to_tax_base_line_dict()
        if self.order_id.is_exchange and self.order_id.rate and self.order_id.rate != 1.0:
            # Apply manual rate to price_unit: price * rate
            res['price_unit'] = res['price_unit'] * self.order_id.rate
        return res
