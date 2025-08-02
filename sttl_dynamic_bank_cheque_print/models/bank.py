from odoo import models, fields, api

class Bank(models.Model):
    _inherit = 'res.bank'

    cheque_background = fields.Binary("Cheque Background Image", default="")
    cheque_width = fields.Integer("Cheque Width", default=800)
    cheque_height = fields.Integer("Cheque Height", default=400)
    font_size = fields.Integer("Font Size", default=14)

    def _get_cheque_render_values(self):
        return {
            'width': self.cheque_width or 100,
            'height': self.cheque_height or 50,
            'font_size': self.font_size or 12,
        }
