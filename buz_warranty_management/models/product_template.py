from odoo import models, fields, api


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    warranty_duration = fields.Integer(
        string='Warranty Duration',
        default=0,
        help='Warranty period from delivery date'
    )
    warranty_period_unit = fields.Selection([
        ('month', 'Month(s)'),
        ('year', 'Year(s)'),
    ], string='Period Unit', default='month', help='Unit for warranty duration')
    warranty_condition = fields.Text(
        string='Warranty Terms & Conditions',
        help='Terms and conditions applicable to this warranty'
    )
    warranty_type = fields.Selection([
        ('replacement', 'Replacement'),
        ('repair', 'Repair'),
        ('refund', 'Refund'),
    ], string='Warranty Type', default='repair')
    service_product_id = fields.Many2one(
        'product.product',
        string='Service Product',
        domain=[('type', '=', 'service')],
        help='Service product used for out-of-warranty repairs'
    )
    allow_out_of_warranty = fields.Boolean(
        string='Allow Out-of-Warranty Service',
        default=True,
        help='Allow creating quotations for expired warranty claims'
    )
    warranty_card_count = fields.Integer(
        string='Warranty Cards',
        compute='_compute_warranty_card_count'
    )

    def _compute_warranty_card_count(self):
        for record in self:
            record.warranty_card_count = self.env['warranty.card'].search_count([
                ('product_id.product_tmpl_id', '=', record.id)
            ])

    def action_view_warranty_cards(self):
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_card').read()[0]
        action['domain'] = [('product_id.product_tmpl_id', '=', self.id)]
        action['context'] = {'default_product_id': self.product_variant_id.id}
        return action
