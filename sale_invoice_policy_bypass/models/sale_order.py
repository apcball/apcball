# -*- coding: utf-8 -*-
from odoo import models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    def _get_invoiceable_lines(self, final=False):
        """
        Override to bypass invoicing policy restrictions.
        All order lines (excluding section/note display types) will be
        included as invoiceable regardless of:
        - invoicing_policy (ordered vs delivered)
        - qty_delivered
        - delivery status
        """
        return self.order_line.filtered(lambda l: not l.display_type)


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _prepare_invoice_line(self, **optional_values):
        """
        Override to force the invoice line quantity to product_uom_qty
        (ordered quantity), ignoring delivered quantity and invoicing policy.
        Already-invoiced quantity is subtracted to avoid double-billing.
        """
        vals = super()._prepare_invoice_line(**optional_values)
        qty = self.product_uom_qty - self.qty_invoiced
        vals['quantity'] = qty if qty > 0 else self.product_uom_qty
        return vals
