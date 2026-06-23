# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class TransferToBufferWizard(models.TransientModel):
    _name = 'buz.marketplace.transfer.to.buffer.wizard'
    _description = 'Transfer to Buffer Location Wizard'

    marketplace_product_id = fields.Many2one('buz.marketplace.product',
        string='Marketplace Product', required=True)
    product_id = fields.Many2one('product.product', string='Product',
        related='marketplace_product_id.product_id', readonly=True)
    current_buffer_stock = fields.Float(string='Current Buffer Stock',
        related='marketplace_product_id.odoo_buffer_stock', readonly=True,
        digits='Product Unit of Measure')
    transfer_qty = fields.Float(string='Quantity to Transfer', required=True,
        digits='Product Unit of Measure')
    source_location_id = fields.Many2one('stock.location',
        string='Source Location', required=True,
        domain="[('usage', '=', 'internal')]")

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            marketplace_product = self.env['buz.marketplace.product'].browse(active_id)
            res['marketplace_product_id'] = active_id
            if marketplace_product.account_id.warehouse_id:
                res['source_location_id'] = \
                    marketplace_product.account_id.warehouse_id.lot_stock_id.id
        return res

    def action_transfer(self):
        self.ensure_one()
        mp = self.marketplace_product_id
        if not mp.product_id:
            raise UserError(_('Marketplace product has no linked Odoo product'))
        if not mp.account_id.buffer_location_id:
            raise UserError(_('Account has no buffer location configured'))
        picking_type = self.env['stock.picking.type'].search([
            ('code', '=', 'internal'),
            ('warehouse_id', '=', mp.account_id.warehouse_id.id),
        ], limit=1)
        if not picking_type:
            raise UserError(_('No internal transfer type found'))
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'location_id': self.source_location_id.id,
            'location_dest_id': mp.account_id.buffer_location_id.id,
            'origin': _('Transfer to Buffer: %s') % mp.marketplace_name,
        })
        self.env['stock.move'].create({
            'name': mp.product_id.display_name,
            'product_id': mp.product_id.id,
            'product_uom_qty': self.transfer_qty,
            'product_uom': mp.product_id.uom_id.id,
            'picking_id': picking.id,
            'location_id': self.source_location_id.id,
            'location_dest_id': mp.account_id.buffer_location_id.id,
        })
        picking.action_confirm()
        picking.action_assign()
        for move_line in picking.move_line_ids:
            move_line.quantity = move_line.move_id.product_uom_qty
            move_line.picked = True
        picking.button_validate()
        self.env['buz.marketplace.stock.history'].create({
            'product_id': mp.product_id.id,
            'account_id': mp.account_id.id,
            'change_type': 'transfer_to_buffer',
            'old_qty': mp.odoo_buffer_stock - self.transfer_qty,
            'new_qty': mp.odoo_buffer_stock,
            'marketplace_qty': mp.marketplace_stock,
            'stock_move_id': picking.move_ids[:1].id if picking.move_ids else False,
            'notes': _('Transferred %s units to buffer location') % self.transfer_qty,
        })
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Transfer Done'),
                'message': _('%s units transferred to buffer') % self.transfer_qty,
                'type': 'success',
                'sticky': False,
            },
        }
