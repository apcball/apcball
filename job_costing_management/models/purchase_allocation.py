# -*- coding: utf-8 -*-

import logging
from odoo import models, fields, api, _

_logger = logging.getLogger(__name__)


class PurchaseAllocation(models.Model):
    _name = 'purchase.allocation'
    _description = 'Purchase Allocation'
    _order = 'id desc'
    _rec_name = 'display_name'

    po_line_id = fields.Many2one(
        'purchase.order.line', string='PO Line',
        required=True, ondelete='cascade', index=True)
    mr_line_id = fields.Many2one(
        'material.requisition.line', string='MR Line',
        required=True, ondelete='restrict', index=True)
    pool_line_id = fields.Many2one(
        'procurement.pool.line', string='Pool Line',
        ondelete='set null', index=True)

    # Quantities
    qty = fields.Float(string='Allocated Qty', required=True)
    qty_received = fields.Float(string='Received Qty', default=0.0)

    # Related fields for easy access
    product_id = fields.Many2one(
        'product.product', string='Product',
        related='po_line_id.product_id', store=True, readonly=True)
    uom_id = fields.Many2one(
        'uom.uom', string='UoM',
        related='po_line_id.product_uom', store=True, readonly=True)

    # Project & cost tracking
    project_id = fields.Many2one(
        'project.project', string='Project', index=True)
    analytic_account_id = fields.Many2one(
        'account.analytic.account', string='Analytic Account', index=True)
    job_cost_sheet_id = fields.Many2one(
        'job.cost.sheet', string='Job Cost Sheet', index=True)

    # Related PO / MR info
    po_id = fields.Many2one(
        'purchase.order', string='Purchase Order',
        related='po_line_id.order_id', store=True, readonly=True)
    mr_id = fields.Many2one(
        'material.requisition', string='Material Requisition',
        related='mr_line_id.requisition_id', store=True, readonly=True)
    mr_name = fields.Char(
        string='MR Number',
        related='mr_id.name', readonly=True)
    project_name = fields.Char(
        string='Project Name',
        related='project_id.name', readonly=True)

    company_id = fields.Many2one(
        'res.company', string='Company',
        related='po_id.company_id', store=True, readonly=True)

    display_name = fields.Char(
        string='Display Name', compute='_compute_display_name')

    @api.depends('po_id', 'mr_id', 'product_id', 'qty')
    def _compute_display_name(self):
        for record in self:
            po_name = record.po_id.name or '?'
            mr_name = record.mr_id.name or '?'
            product_name = record.product_id.display_name or '?'
            record.display_name = '%s → %s: %s x %s' % (
                mr_name, po_name, product_name, record.qty)

    def update_received_qty(self, qty):
        """Update the received qty for this allocation."""
        self.ensure_one()
        self.qty_received = min(self.qty_received + qty, self.qty)

        # Check if all allocations for the pool line are fully received
        if self.pool_line_id:
            pool_line = self.pool_line_id
            # Trigger recompute
            pool_line._compute_quantities()

            # Check if all pool lines are done
            pool = pool_line.pool_id
            if all(line.remaining_qty <= 0 for line in pool.line_ids):
                pool.action_done()
