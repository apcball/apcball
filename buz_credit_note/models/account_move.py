from odoo import models, fields

class AccountMove(models.Model):
    _inherit = 'account.move'

    custom_document_number = fields.Char(string='Custom Document Number', readonly=True)
    custom_return_number = fields.Char(string='Custom Return Number', readonly=True)
    ref = fields.Char(string='Reference')