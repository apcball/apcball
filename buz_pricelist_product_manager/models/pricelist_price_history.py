from odoo import models, fields

class PricelistPriceHistory(models.Model):
    _name = 'pricelist.price.history'
    _description = 'Pricelist Price History'
    _order = 'create_date desc'

    product_tmpl_id = fields.Many2one('product.template', string='Product Template', readonly=True)
    product_id = fields.Many2one('product.product', string='Product Variant', readonly=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', readonly=True)
    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user, readonly=True)
    date_change = fields.Datetime(string='Date', default=fields.Datetime.now, readonly=True)
    
    old_price = fields.Float(string='Old Price', readonly=True)
    new_price = fields.Float(string='New Price', readonly=True)
    
    old_installation_price = fields.Float(string='Old Install Price', readonly=True)
    new_installation_price = fields.Float(string='New Install Price', readonly=True)
    
    origin = fields.Selection([
        ('create', 'Created'),
        ('update', 'Updated')
    ], string='Action', readonly=True)
