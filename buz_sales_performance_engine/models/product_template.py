from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = "product.template"

    spe_exclude_from_sales = fields.Boolean(
        string="Exclude from Sales Dashboard",
        help="Invoice lines of this product are left out of the Invoice "
             "figure on the Sales Performance dashboard (deposits, card "
             "fees and other lines that are not real sales).",
    )
