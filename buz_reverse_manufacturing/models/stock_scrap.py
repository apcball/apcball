# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import fields, models


class StockScrap(models.Model):
    _inherit = 'stock.scrap'

    reverse_recovery_line_id = fields.Many2one(
        'buz.reverse.recovery.line',
        string='Reverse Recovery Line',
        readonly=True,
        index=True,
        copy=False,
        help='Recovery line whose shortfall generated this scrap.',
    )
