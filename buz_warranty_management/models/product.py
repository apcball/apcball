from odoo import models, fields, api


class ProductProduct(models.Model):
    _inherit = 'product.product'

    warranty_card_count = fields.Integer(
        string='Warranty Cards',
        related='product_tmpl_id.warranty_card_count',
        readonly=True
    )

    def action_view_warranty_cards(self):
        """
        Action to view warranty cards for this product variant.
        Delegates to the template method since warranty cards are linked to templates.
        """
        self.ensure_one()
        return self.product_tmpl_id.action_view_warranty_cards()