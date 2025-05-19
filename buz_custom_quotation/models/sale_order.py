from odoo import api, fields, models

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    purchase_price = fields.Float(string='Purchase Price', digits='Product Price')

    @api.onchange('product_id')
    def _onchange_product_id_set_purchase_price(self):
        if self.product_id:
            self.purchase_price = self.product_id.standard_price

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    proposal_no = fields.Char(string='Proposal Number', readonly=True, copy=False)
    project_name = fields.Char(string='Project Name')
    customer_name = fields.Char(string='Customer Name')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('proposal_no'):
                sequence = self.env['ir.sequence'].next_by_code('sale.proposal')
                if sequence:
                    vals['proposal_no'] = sequence
                elif vals.get('name'):
                    vals['proposal_no'] = vals['name'].replace('SO', 'PS')
        records = super().create(vals_list)
        return records

    def write(self, vals):
        if 'name' in vals and not self.proposal_no:
            sequence = self.env['ir.sequence'].next_by_code('sale.proposal')
            if sequence:
                vals['proposal_no'] = sequence
            else:
                vals['proposal_no'] = vals['name'].replace('SO', 'PS')
        return super().write(vals)