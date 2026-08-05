# Part of buz addons for Mogen Co. See LICENSE file.
from odoo import fields, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    reverse_recovery_line_id = fields.Many2one(
        'buz.reverse.recovery.line',
        string='Reverse Recovery Line',
        index=True,
        copy=False,
        help='Recovery line of the Reverse Manufacturing Order that '
             'generated this move. Carries the cost allocation share.',
    )
