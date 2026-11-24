# -*- coding: utf-8 -*-
"""
Product Model Extension for FIFO by Warehouse

Overrides _get_fifo_candidates to filter by warehouse.
"""

import json

from odoo import models
import logging

_logger = logging.getLogger(__name__)


class ProductProduct(models.Model):
    """
    Extension of product.product to support per-warehouse FIFO tracking.
    
    This override ensures that _get_fifo_candidates() only returns candidates
    from the correct warehouse, preventing cross-warehouse FIFO consumption.
    """
    
    _inherit = 'product.product'
    
    def _get_fifo_candidates(self, company):
        """
        🔴 CRITICAL OVERRIDE: Filter FIFO candidates by warehouse.
        
        Odoo standard _get_fifo_candidates() returns ALL layers across all warehouses.
        This override filters to only return layers from the specific warehouse
        being processed.
        
        The warehouse context is passed via 'fifo_warehouse_id' key.
        
        Returns:
            Recordset of stock.valuation.layer filtered by warehouse
        """
        self.ensure_one()
        
        # Get warehouse from context
        warehouse_id = self.env.context.get('fifo_warehouse_id')
        
        if not warehouse_id:
            # No warehouse scope: core would consume layers of EVERY warehouse
            # (root cause of cross-warehouse FIFO drift). 'warn' keeps the legacy
            # behaviour; 'block' returns no candidates so the shortage path
            # (negative layer / shortage_policy) applies and other warehouses'
            # layers stay untouched.
            mode = self.env['ir.config_parameter'].sudo().get_param(
                'stock_fifo_by_location.unscoped_fifo_mode', 'warn')
            _logger.warning(
                "_get_fifo_candidates() called without fifo_warehouse_id in context! "
                "Product: %s, mode=%s.", self.display_name, mode,
            )
            if mode == 'block':
                return self.env['stock.valuation.layer']
            return super()._get_fifo_candidates(company)

        _logger.debug(
            f"🔍 _get_fifo_candidates() for Product={self.display_name}, "
            f"Warehouse ID={warehouse_id}, Company={company.name}"
        )
        
        # Build domain with warehouse filter
        domain = [
            ('product_id', '=', self.id),
            ('remaining_qty', '>', 0),
            ('company_id', '=', company.id),
            ('warehouse_id', '=', warehouse_id),  # 🔴 KEY: Filter by warehouse
        ]
        
        candidates = self.env['stock.valuation.layer'].search(
            domain,
            order='create_date, id'
        )
        
        _logger.debug(
            f"✅ Found {len(candidates)} FIFO candidates at warehouse_id={warehouse_id}"
        )
        
        if candidates:
            for c in candidates[:5]:  # Log first 5
                _logger.debug(
                    f"  - Layer {c.id}: qty={c.quantity}, "
                    f"remaining={c.remaining_qty}, "
                    f"warehouse={c.warehouse_id.name if c.warehouse_id else 'None'}"
                )

        # Audit trail: the queue head core _run_fifo() will price from, so a
        # delivery cost that disagrees with a FIFO replay can be traced.
        _logger.info(
            "FIFO queue product=%s wh=%s n=%s head=%s",
            self.id, warehouse_id, len(candidates),
            [
                (c.id, c.remaining_qty, round(c.remaining_value, 2), str(c.create_date)[:19])
                for c in candidates[:15]
            ],
        )

        return candidates

    def _run_fifo_vacuum(self, company=None):
        """Vacuum each warehouse queue separately so a negative layer is never
        compensated with another warehouse's layers. Negative layers without a
        warehouse are only compensated by layers without a warehouse."""
        if self.env.context.get('fifo_vacuum_warehouse_id'):
            return super()._run_fifo_vacuum(company)
        company = company or self.env.company
        negatives = self.env['stock.valuation.layer'].sudo().search([
            ('product_id', 'in', self.ids),
            ('remaining_qty', '<', 0),
            ('stock_move_id', '!=', False),
            ('company_id', '=', company.id),
        ])
        buckets = set(negatives.mapped('warehouse_id').ids)
        if negatives.filtered(lambda l: not l.warehouse_id):
            buckets.add('none')  # layers without warehouse only meet each other
        for wh_id in sorted(buckets, key=str):
            super(ProductProduct, self.with_context(fifo_vacuum_warehouse_id=wh_id))\
                ._run_fifo_vacuum(company)

    def _prepare_out_svl_vals(self, quantity, company, lot=False, location=False):
        """Scope the FIFO queue of an outgoing layer to the warehouse of the
        source location when the caller did not set 'fifo_warehouse_id'."""
        self.ensure_one()
        if (not self.env.context.get('fifo_warehouse_id') and location
                and location.warehouse_id):
            self = self.with_context(fifo_warehouse_id=location.warehouse_id.id)
        return super(ProductProduct, self)._prepare_out_svl_vals(
            quantity, company, lot=lot, location=location)

    def _prepare_internal_out_svl_vals(self, quantity, company, move=False):
        """Record which cost origins an inter-warehouse transfer really consumes.

        stock_by_locations builds the transfer-out layer through _run_fifo, which
        updates the candidate layers without linking the consumption to the layer
        being created. Diff the candidates' remaining_qty around super() and store
        the result (origin, qty, value) on the out layer, so the destination position
        layers can be split per origin and carry the cost actually consumed (see stock.move._ensure_inter_warehouse_valuation_layers).
        """
        self.ensure_one()
        # Scope the FIFO queue to the warehouse the goods leave: without the key
        # _get_fifo_candidates falls back to every warehouse.
        if move and move.location_id.warehouse_id:
            self = self.with_context(fifo_warehouse_id=move.location_id.warehouse_id.id)
        snapshot = {}
        if self.cost_method == 'fifo':
            snapshot = {
                cand.id: (cand.remaining_qty, cand.remaining_value)
                for cand in self._get_fifo_candidates(company)
            }
        vals = super()._prepare_internal_out_svl_vals(quantity, company, move=move)
        if snapshot:
            consumed = {}  # origin layer id -> [qty, value]
            for cand in self.env['stock.valuation.layer'].browse(list(snapshot)):
                before_qty, before_value = snapshot[cand.id]
                taken = before_qty - cand.remaining_qty
                if taken > 0:
                    origin_id = (cand.origin_valuation_layer_id or cand).id
                    entry = consumed.setdefault(origin_id, [0.0, 0.0])
                    entry[0] += taken
                    entry[1] += before_value - cand.remaining_value
            if consumed:
                vals['consumed_origin_splits'] = json.dumps(
                    [[oid, qty, value] for oid, (qty, value) in consumed.items()]
                )
        return vals
