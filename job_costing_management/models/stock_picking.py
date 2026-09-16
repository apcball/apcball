# -*- coding: utf-8 -*-

from odoo import models, api, _
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def button_validate(self):
        """Update allocations and complete linked material requisitions."""
        result = super(StockPicking, self).button_validate()

        for picking in self:
            if picking.picking_type_code != 'incoming':
                continue

            for move in picking.move_ids.filtered(lambda m: m.state == 'done'):
                po_line = move.purchase_line_id
                if not po_line:
                    continue

                # Find allocations for this PO line
                allocations = self.env['purchase.allocation'].search([
                    ('po_line_id', '=', po_line.id),
                ])
                if not allocations:
                    continue

                # Get received qty for this move
                qty_done = move.quantity if hasattr(move, 'quantity') else move.quantity_done

                # Distribute received qty across allocations proportionally
                total_alloc_pending = sum(
                    max(a.qty - a.qty_received, 0) for a in allocations)

                if total_alloc_pending <= 0:
                    continue

                remaining_to_distribute = qty_done
                for alloc in allocations:
                    pending = alloc.qty - alloc.qty_received
                    if pending <= 0:
                        continue

                    # Proportional share or whatever is left
                    share = min(pending, remaining_to_distribute)
                    if share > 0:
                        alloc.update_received_qty(share)
                        remaining_to_distribute -= share

                    if remaining_to_distribute <= 0:
                        break

                if remaining_to_distribute > 0:
                    _logger.info(
                        'Picking %s: %.2f units of %s received beyond '
                        'allocated qty for PO line %s',
                        picking.name, remaining_to_distribute,
                        move.product_id.display_name, po_line.order_id.name)

        requisition_lines = self.env['material.requisition.line'].search([
            ('picking_ids', 'in', self.ids),
        ])
        requisition_lines.mapped('requisition_id').sudo()._check_and_mark_done()

        return result
