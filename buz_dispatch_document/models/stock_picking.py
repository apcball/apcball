from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    buz_dispatch_document_ids = fields.One2many(
        'buz.dispatch.document',
        'stock_picking_id',
        string='Dispatch Documents',
    )

    buz_dispatch_document_count = fields.Integer(
        string='Dispatch Document Count',
        compute='_compute_buz_dispatch_document_count',
    )

    @api.depends('buz_dispatch_document_ids')
    def _compute_buz_dispatch_document_count(self):
        for picking in self:
            picking.buz_dispatch_document_count = len(picking.buz_dispatch_document_ids)