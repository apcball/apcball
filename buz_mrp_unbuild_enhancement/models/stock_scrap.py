# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    unbuild_id = fields.Many2one(
        'mrp.unbuild',
        string='Unbuild Order',
        index=True,
        readonly=True,
        help='Unbuild order that generated this scrap.',
    )
