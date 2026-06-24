from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    picking_display_name = fields.Char(
        string='Display Name',
        compute='_compute_picking_display_name',
    )

    @api.depends('name')
    def _compute_picking_display_name(self):
        for picking in self:
            if 'buz_dispatch_document_name' in picking._fields:
                picking.picking_display_name = picking.buz_dispatch_document_name or picking.name
            else:
                picking.picking_display_name = picking.name
