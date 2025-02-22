from odoo import models, api
from bahttext import bahttext
from num2words import num2words

class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def amount_to_text_th(self):
        """Convert amount to Thai text"""
        return bahttext(self.amount_total)

    def amount_to_text_en(self):
        """Convert amount to English text"""
        amount_in_words = num2words(self.amount_total, lang='en')
        currency_name = self.currency_id.name or ''

        # Format the first letter of each word to uppercase and add currency
        amount_text = amount_in_words.title()

        # Handle decimal part
        amount_float = self.amount_total
        decimal_part = round((amount_float - int(amount_float)) * 100)

        if decimal_part > 0:
            decimal_words = num2words(decimal_part, lang='en').title()
            final_text = f"{amount_text} {currency_name} and {decimal_words} Cents Only"
        else:
            final_text = f"{amount_text} {currency_name} Only"

        return final_text