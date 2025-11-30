# -*- coding: utf-8 -*-
"""
Product Model Extension for FIFO by Warehouse

Overrides _get_fifo_candidates to filter by warehouse.
"""

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
            _logger.warning(
                f"⚠️ _get_fifo_candidates() called without fifo_warehouse_id in context! "
                f"Product: {self.display_name}. This will return candidates from ALL warehouses. "
                f"This should not happen in per-warehouse FIFO mode."
            )
            # Fallback to standard behavior
            return super()._get_fifo_candidates(company)
        
        _logger.error(
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
        
        _logger.error(
            f"✅ Found {len(candidates)} FIFO candidates at warehouse_id={warehouse_id}"
        )
        
        if candidates:
            for c in candidates[:5]:  # Log first 5
                _logger.error(
                    f"  - Layer {c.id}: qty={c.quantity}, "
                    f"remaining={c.remaining_qty}, "
                    f"warehouse={c.warehouse_id.name if c.warehouse_id else 'None'}"
                )
        
        return candidates
