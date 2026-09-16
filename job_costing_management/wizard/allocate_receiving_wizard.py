# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class AllocateReceivingWizard(models.TransientModel):
    _name = 'allocate.receiving.wizard'
    _description = 'Allocate Received Goods to Projects'

    picking_id = fields.Many2one(
        'stock.picking', string='Receipt', required=True, readonly=True)

    line_ids = fields.One2many(
        'allocate.receiving.wizard.line', 'wizard_id',
        string='Allocation Lines')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        picking_id = self.env.context.get('active_id')
        if picking_id:
            picking = self.env['stock.picking'].browse(picking_id)
            res['picking_id'] = picking.id

            lines = []
            for move in picking.move_ids:
                # Find PO line
                po_line = move.purchase_line_id
                if not po_line:
                    continue

                # Find allocations for this PO line
                allocations = self.env['purchase.allocation'].search([
                    ('po_line_id', '=', po_line.id),
                ])

                if not allocations:
                    continue

                # Calculate remaining to allocate for this move
                qty_done = move.quantity if hasattr(move, 'quantity') else move.quantity_done

                for alloc in allocations:
                    remaining_to_receive = alloc.qty - alloc.qty_received
                    if remaining_to_receive <= 0:
                        continue

                    suggest_qty = min(remaining_to_receive, qty_done)
                    if suggest_qty <= 0:
                        continue

                    lines.append((0, 0, {
                        'allocation_id': alloc.id,
                        'product_id': alloc.product_id.id,
                        'mr_name': alloc.mr_name,
                        'project_id': alloc.project_id.id,
                        'allocated_qty': alloc.qty,
                        'already_received': alloc.qty_received,
                        'qty_to_receive': suggest_qty,
                    }))
                    qty_done -= suggest_qty

            res['line_ids'] = lines

        return res

    def action_confirm_allocation(self):
        """Confirm the allocation of received goods."""
        self.ensure_one()

        for line in self.line_ids:
            if line.qty_to_receive <= 0:
                continue

            alloc = line.allocation_id
            alloc.update_received_qty(line.qty_to_receive)

        return {'type': 'ir.actions.act_window_close'}


class AllocateReceivingWizardLine(models.TransientModel):
    _name = 'allocate.receiving.wizard.line'
    _description = 'Allocate Receiving Wizard Line'

    wizard_id = fields.Many2one(
        'allocate.receiving.wizard', string='Wizard',
        required=True, ondelete='cascade')

    allocation_id = fields.Many2one(
        'purchase.allocation', string='Allocation',
        required=True)

    product_id = fields.Many2one(
        'product.product', string='Product', readonly=True)
    mr_name = fields.Char(string='MR Reference', readonly=True)
    project_id = fields.Many2one(
        'project.project', string='Project', readonly=True)

    allocated_qty = fields.Float(string='Allocated Qty', readonly=True)
    already_received = fields.Float(string='Already Received', readonly=True)
    qty_to_receive = fields.Float(string='Qty to Receive')
