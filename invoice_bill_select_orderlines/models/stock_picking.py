# -*- coding: utf-8 -*-
"""Auto-select billable PO lines after goods receipt validation."""

from odoo import models


class StockPicking(models.Model):
    """Inherit stock picking to auto-select invoice lines after receipt."""
    _inherit = 'stock.picking'

    def _select_billable_purchase_lines(self):
        """Select billable PO lines for completed incoming receipts."""
        done_receipts = self.filtered(
            lambda picking: picking.state == 'done'
            and picking.picking_type_id.code == 'incoming'
            and picking.purchase_id
        )
        done_receipts.purchase_id.order_line.filtered(
            lambda line: line.qty_to_invoice > 0 and not line.display_type
        ).write({'is_product_select': True})

    def button_validate(self):
        """Keep support for flows that finish directly from validate."""
        res = super().button_validate()
        self._select_billable_purchase_lines()
        return res

    def _action_done(self):
        """Ensure PO lines are selected after receipt completion in all flows."""
        res = super()._action_done()
        self._select_billable_purchase_lines()
        return res
