from odoo import models, fields, api

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    project_name = fields.Char(string='Project Name')
    sale_header = fields.Binary(related='company_id.sale_header', string='Header Template', readonly=True)
    sale_footer = fields.Binary(related='company_id.sale_footer', string='Footer Template', readonly=True)