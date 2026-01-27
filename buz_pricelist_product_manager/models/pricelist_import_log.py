from odoo import models, fields

class PricelistImportLog(models.Model):
    _name = 'pricelist.import.log'
    _description = 'Pricelist Import Log'
    _order = 'create_date desc'

    user_id = fields.Many2one('res.users', string='User', default=lambda self: self.env.user, readonly=True)
    pricelist_id = fields.Many2one('product.pricelist', string='Pricelist', required=True, readonly=True)
    datetime = fields.Datetime(string='Date', default=fields.Datetime.now, readonly=True)
    total_rows = fields.Integer(string='Total Rows', readonly=True)
    updated_count = fields.Integer(string='Updated', readonly=True)
    created_count = fields.Integer(string='Created', readonly=True)
    skipped_count = fields.Integer(string='Skipped', readonly=True)
    file_name = fields.Char(string="File Name")
