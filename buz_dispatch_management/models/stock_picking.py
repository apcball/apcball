from odoo import api, fields, models


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    buz_dispatch_document_ids = fields.One2many(
        'buz.dispatch.document',
        'picking_id',
        string='Dispatch Documents',
    )

    buz_dispatch_document_count = fields.Integer(
        string='Dispatch Document Count',
        compute='_compute_buz_dispatch_document_count',
    )

    dispatch_state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('printed', 'Printed'),
            ('in_transit', 'In Transit'),
            ('delivered', 'Delivered'),
            ('posted', 'Posted'),
        ],
        string='Dispatch State',
        compute='_compute_dispatch_state',
        store=True,
    )

    has_dispatch = fields.Boolean(
        string='Has Dispatch',
        compute='_compute_has_dispatch',
    )

    @api.depends('buz_dispatch_document_ids')
    def _compute_buz_dispatch_document_count(self):
        for picking in self:
            picking.buz_dispatch_document_count = len(picking.buz_dispatch_document_ids)

    @api.depends('buz_dispatch_document_ids.state')
    def _compute_has_dispatch(self):
        for picking in self:
            picking.has_dispatch = bool(picking.buz_dispatch_document_ids)

    @api.depends('buz_dispatch_document_ids.state')
    def _compute_dispatch_state(self):
        state_order = ['draft', 'printed', 'in_transit', 'delivered', 'posted']
        for picking in self:
            states = picking.buz_dispatch_document_ids.filtered(
                lambda d: d.state != 'cancel'
            ).mapped('state')
            if not states:
                picking.dispatch_state = False
            else:
                picking.dispatch_state = max(states, key=lambda s: state_order.index(s))

    def action_create_dispatch(self):
        self.ensure_one()
        action = self.env.ref('buz_dispatch_management.action_create_dispatch_wizard').read()[0]
        action['context'] = {
            'default_picking_id': self.id,
            'default_partner_id': self.partner_id.id,
            'default_sale_id': self.sale_id.id,
        }
        return action
