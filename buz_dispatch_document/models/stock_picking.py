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

    buz_dispatch_document_name = fields.Char(
        string='Dispatch Document',
        compute='_compute_buz_dispatch_document_name',
        search='_search_buz_dispatch_document_name',
    )

    @api.depends('buz_dispatch_document_ids')
    def _compute_buz_dispatch_document_count(self):
        for picking in self:
            picking.buz_dispatch_document_count = len(picking.buz_dispatch_document_ids)

    @api.depends('buz_dispatch_document_ids.name')
    def _compute_buz_dispatch_document_name(self):
        for picking in self:
            names = picking.buz_dispatch_document_ids.mapped('name')
            picking.buz_dispatch_document_name = ', '.join(n for n in names if n)

    def _search_buz_dispatch_document_name(self, operator, value):
        return [('buz_dispatch_document_ids.name', operator, value)]