from odoo import models, fields


class ProductCategory(models.Model):
    _inherit = 'product.category'

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
        ('replacement', 'Replace'),
        ('repair', 'Repair'),
        ('refund', 'Refund'),
    ], string='Warranty Type', default='replacement')
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
