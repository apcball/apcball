from odoo import api, fields, models, _
import re

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    multi_discount = fields.Char(string='Discounts (%)', help="Multiple discounts, separated by '+' sign. e.g. 10+5+2")

    @api.depends('multi_discount', 'price_unit', 'product_uom_qty', 'product_id', 'order_id.partner_id', 'order_id.currency_id', 'order_id.company_id')
    def _compute_amount(self):
        for line in self:
            price = line.price_unit
            if line.multi_discount:
                discounts = line.multi_discount.split('+')
                for discount in discounts:
                    if discount.strip() and discount.strip().replace('.', '', 1).isdigit():
                        price = price * (1 - (float(discount) / 100))
                # Set the standard discount field for compatibility
                line.discount = self._get_equivalent_discount(line.price_unit, price)
            super(SaleOrderLine, line)._compute_amount()

    @api.onchange('multi_discount')
    def _onchange_multi_discount(self):
        if self.multi_discount:
            # Validate format (only numbers and + signs)
            if not re.match(r'^(\d+(\.\d+)?)((\+\d+(\.\d+)?)+)?$', self.multi_discount):
                return {'warning': {'title': _('Warning'), 'message': _('Invalid discount format. Use numbers separated by + sign (e.g. 10+5+2)')}}

            # Calculate equivalent single discount
            price = self.price_unit
            discounts = self.multi_discount.split('+')
            for discount in discounts:
                if discount.strip() and discount.strip().replace('.', '', 1).isdigit():
                    price = price * (1 - (float(discount) / 100))

            # Set the standard discount field for compatibility
            self.discount = self._get_equivalent_discount(self.price_unit, price)

    def _get_equivalent_discount(self, original_price, final_price):
        if original_price:
            return (1 - (final_price / original_price)) * 100
        return 0.0