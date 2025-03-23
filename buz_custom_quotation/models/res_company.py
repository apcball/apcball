from odoo import models, fields

class ResCompany(models.Model):
    _inherit = 'res.company'

    sale_header = fields.Binary(string='Sale Header Template')
    sale_footer = fields.Binary(string='Sale Footer Template')