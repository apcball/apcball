from odoo import models, api
from bahttext import bahttext

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def amount_to_text_th(self):
        """Convert amount to Thai text"""
        return bahttext(self.amount_total)

    def amount_to_text_en(self):
        """Convert amount to English text"""
        # ... existing English conversion code ...