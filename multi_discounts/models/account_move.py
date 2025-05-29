from odoo import api, fields, models, _
import re

class AccountMoveLine(models.Model):
    _inherit = 'account.move.line'

    multi_discount = fields.Char(string='Discounts (%)', help="Multiple discounts, separated by '+' sign. e.g. 10+5+2")

    @api.depends('multi_discount', 'price_unit', 'quantity', 'product_id', 'move_id.partner_id', 'move_id.currency_id')
    def _compute_price(self):
        super(AccountMoveLine, self)._compute_price()
        for line in self:
            if line.multi_discount:
                price = line.price_unit
                discounts = line.multi_discount.split('+')
                for discount in discounts:
                    if discount.strip() and discount.strip().replace('.', '', 1).isdigit():
                        price = price * (1 - (float(discount) / 100))
                # Set the standard discount field for compatibility
                line.discount = self._get_equivalent_discount(line.price_unit, price)
                # Update price_subtotal based on the computed discount
                line.price_subtotal = price * line.quantity

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

    @api.model
    def _prepare_add_missing_fields(self, values):
        """ Inject the multi_discount from the sale order line when creating invoice line """
        values = super()._prepare_add_missing_fields(values)
        if values.get('sale_line_ids'):
            sale_line = self.env['sale.order.line'].browse(values['sale_line_ids'][0][1])
            if sale_line.multi_discount:
                values['multi_discount'] = sale_line.multi_discount
        return values

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if 'sale_line_ids' in vals:
                sale_line_ids = vals.get('sale_line_ids', [])[0][1]
                if sale_line_ids:
                    sale_line = self.env['sale.order.line'].browse(sale_line_ids)
                    if sale_line.multi_discount:
                        vals['multi_discount'] = sale_line.multi_discount
        return super().create(vals_list)