from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    warranty_duration_override = fields.Integer(
        string='Product Warranty Duration',
        default=0,
        help='Warranty duration used when overriding the category setting.',
    )
    warranty_period_unit_override = fields.Selection([
        ('month', 'Month(s)'),
        ('year', 'Year(s)'),
    ], string='Product Warranty Period Unit', default='month')
    warranty_duration = fields.Integer(
        string='Warranty Duration',
        compute='_compute_warranty_period',
        store=True,
        readonly=True,
    )
    warranty_period_unit = fields.Selection([
        ('month', 'Month(s)'),
        ('year', 'Year(s)'),
    ], string='Period Unit', compute='_compute_warranty_period', store=True, readonly=True)
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

    @api.depends(
        'warranty_duration_override',
        'warranty_period_unit_override',
        'categ_id.warranty_duration',
        'categ_id.warranty_period_unit',
    )
    def _compute_warranty_period(self):
        for record in self:
            if record.warranty_duration_override:
                record.warranty_duration = record.warranty_duration_override
                record.warranty_period_unit = record.warranty_period_unit_override
            else:
                record.warranty_duration = record.categ_id.warranty_duration
                record.warranty_period_unit = record.categ_id.warranty_period_unit

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
