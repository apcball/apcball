from odoo import fields, models


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    is_nc_tag = fields.Boolean(
        string='NC Tag',
        help='Show the "Print NC Tag" button on transfers of this operation type.',
    )
