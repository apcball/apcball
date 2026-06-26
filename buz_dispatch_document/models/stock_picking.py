from odoo import api, fields, models, _
from odoo.exceptions import UserError


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

    def action_create_dispatch_document(self):
        # Allow only deliveries originating from a Sales Order
        no_sale = self.filtered(lambda p: not p.sale_id)
        if no_sale:
            raise UserError(
                _('Dispatch documents can only be created from deliveries '
                  'that originate from a Sales Order.\nInvalid: %s')
                % ', '.join(no_sale.mapped('name'))
            )
        wrong_state = self.filtered(lambda p: p.state not in ('confirmed', 'assigned'))
        if wrong_state:
            raise UserError(
                _('Delivery orders must be Available or Waiting before '
                  'creating a Dispatch Document.\nInvalid: %s')
                % ', '.join(wrong_state.mapped('name'))
            )
        eligible = self.filtered(lambda p: not p.buz_dispatch_document_ids)
        if not eligible:
            raise UserError(
                _('All selected deliveries already have dispatch documents.')
            )
        dispatches = self.env['buz.dispatch.document'].create([
            {'stock_picking_id': picking.id}
            for picking in eligible
        ])
        if len(dispatches) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'buz.dispatch.document',
                'res_id': dispatches.id,
                'view_mode': 'form',
                'target': 'current',
            }
        action = self.env.ref('buz_dispatch_document.action_buz_dispatch_document').read()[0]
        action['domain'] = [('id', 'in', dispatches.ids)]
        action['target'] = 'current'
        return action