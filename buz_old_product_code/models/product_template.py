from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    old_product_code = fields.Char(
        string='Old Product Code',
        help='Reference code from old system',
        index=True,  # Adding index for better search performance
    )

    _sql_constraints = [
        ('old_product_code_uniq', 'unique(old_product_code)',
         'Old Product Code must be unique!')
    ]

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        args = args or []
        if name:
            args = ['|',
                   ('old_product_code', operator, name),
                   ('name', operator, name)] + args
        return super(ProductTemplate, self).name_search(
            name=name, args=args, operator=operator, limit=limit)