from odoo import models, fields


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    warranty_duration = fields.Integer(
        string='Warranty Duration',
        related='categ_id.warranty_duration',
        readonly=True
    )
    warranty_period_unit = fields.Selection([
        ('month', 'Month(s)'),
        ('year', 'Year(s)'),
    ], string='Period Unit', related='categ_id.warranty_period_unit', readonly=True)
    warranty_condition = fields.Text(
        string='Warranty Terms & Conditions',
        related='categ_id.warranty_condition',
        readonly=True
    )
    warranty_type = fields.Selection([
        ('replacement', 'Replacement'),
        ('repair', 'Repair'),
        ('refund', 'Refund'),
    ], string='Warranty Type', related='categ_id.warranty_type', readonly=True)
    service_product_id = fields.Many2one(
        'product.product',
        string='Service Product',
        related='categ_id.service_product_id',
        readonly=True
    )
    allow_out_of_warranty = fields.Boolean(
        string='Allow Out-of-Warranty Service',
        related='categ_id.allow_out_of_warranty',
        readonly=True
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
