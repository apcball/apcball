# -*- coding: utf-8 -*-

from odoo import models, fields, api


class AccountMove(models.Model):
    """Extend Account Move to track source PO/SO for credit notes"""

    _inherit = 'account.move'

    # Track source orders for credit notes
    source_po_id = fields.Many2one(
        'purchase.order',
        string='Source PO',
        readonly=True,
        help='Source Purchase Order that created this credit note'
    )
    source_so_id = fields.Many2one(
        'sale.order',
        string='Source SO',
        readonly=True,
        help='Source Sale Order that created this credit note'
    )
    source_line_ids = fields.Text(
        string='Source Lines',
        readonly=True,
        help='JSON tracking of source order lines'
    )

    def name_get(self):
        """Add source order reference to credit note name"""
        result = []
        for move in self:
            if move.move_type in ['in_refund', 'out_refund'] and (move.source_po_id or move.source_so_id):
                ref = ''
                if move.source_po_id:
                    ref = f'CN/{move.source_po_id.name}'
                elif move.source_so_id:
                    ref = f'CN/{move.source_so_id.name}'
                result.append((move.id, f"{ref} ({move.name})"))
            else:
                result.append((move.id, move.name))
        return result
