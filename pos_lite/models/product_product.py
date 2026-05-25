from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    can_be_pos = fields.Boolean(string='Can be POS', default=False)


class ProductProduct(models.Model):
    _inherit = 'product.product'

    can_be_pos = fields.Boolean(
        string='Can be POS',
        related='product_tmpl_id.can_be_pos',
        readonly=False
    )

    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        if not self.env.context.get('pos_lite_search'):
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        args = list(args or [])
        name = (name or '').strip()
        if not name:
            return super().name_search(name=name, args=args, operator=operator, limit=limit)

        domain = [
            '|', '|', '|', '|',
            ('default_code', '=', name),
            ('barcode', '=', name),
            ('default_code', operator, name),
            ('barcode', operator, name),
            ('name', operator, name),
        ]
        products = self.search(domain + args, limit=limit)
        return products.name_get() if products else super().name_search(name=name, args=args, operator=operator, limit=limit)
