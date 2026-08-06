from odoo import fields, models


class BuzItStockHistoryRequest(models.Model):
    _inherit = 'buz.it.stock.history'

    request_line_id = fields.Many2one(
        'buz.it.consumable.request.line',
        string='Request Line',
        ondelete='set null',
        index=True,
    )
