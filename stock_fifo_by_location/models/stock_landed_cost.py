# -*- coding: utf-8 -*-
"""
Stock Landed Cost Model Extension

This module extends stock.landed.cost to support per-location landed cost allocation.
When landed costs are applied to inventory at a specific location, the module ensures
that these costs are properly tracked and allocated proportionally during internal
transfers.
"""

from odoo import models, fields, api
from odoo.tools import float_round, float_compare


class StockLandedCost(models.Model):
    """
    Extension of stock.landed.cost to support per-location tracking.
    
    When a landed cost is posted, it creates allocations in 
    stock.valuation.layer.landed.cost to track the cost at each location.
    """
    
    _inherit = 'stock.landed.cost'
    
    location_landed_cost_ids = fields.One2many(
        'stock.valuation.layer.landed.cost',
        'landed_cost_id',
        string='Location-based Landed Costs',
        help='Per-location breakdown of this landed cost.',
        readonly=True
    )
    
    @api.model
    def create(self, vals):
        """Create landed cost record."""
        record = super().create(vals)
        return record
    
    def button_validate(self):
        """
        Override validation to create per-location landed cost allocations.
        """
        # Call parent validation
        result = super().button_validate()
        
        # After parent validation, create location-specific allocations
        self._allocate_landed_costs_by_location()
        
        return result
    
    def _allocate_landed_costs_by_location(self):
        """
        Create per-location landed cost allocations.
        
        For each valuation adjustment line with a landed cost, create or update
        stock.valuation.layer.landed.cost records to track the cost at the
        specific location where the goods are received.
        """
        lc_location_model = self.env['stock.valuation.layer.landed.cost']
        precision = self.env['decimal.precision'].precision_get('Product Price')
        
        for landed_cost in self:
            if landed_cost.state != 'done':
                continue
            
            for val_adj_line in landed_cost.valuation_adjustment_lines:
                if not val_adj_line.move_id:
                    continue
                
                move = val_adj_line.move_id
                product = move.product_id
                location = move.location_dest_id  # Where the goods arrived
                company = landed_cost.company_id
                lc_value = val_adj_line.additional_landed_cost
                qty = move.product_uom._compute_quantity(
                    move.quantity, move.product_id.uom_id
                )
                
                # Find or create valuation layer for this move at the location
                # The valuation layer should exist if landed costs are applied after receipt
                svl_records = self.env['stock.valuation.layer'].search([
                    ('stock_move_id', '=', move.id),
                    ('location_id', '=', location.id),
                ], limit=1)
                
                if svl_records:
                    svl = svl_records[0]
                    
                    # Check if allocation already exists
                    existing = lc_location_model.search([
                        ('valuation_layer_id', '=', svl.id),
                        ('location_id', '=', location.id),
                        ('landed_cost_id', '=', landed_cost.id),
                    ], limit=1)
                    
                    if existing:
                        # Update if already exists
                        existing.landed_cost_value = float_round(lc_value, precision_digits=precision)
                        existing.quantity = qty
                    else:
                        # Create new allocation
                        lc_location_model.create({
                            'valuation_layer_id': svl.id,
                            'location_id': location.id,
                            'landed_cost_id': landed_cost.id,
                            'valuation_adjustment_line_id': val_adj_line.id,
                            'landed_cost_value': float_round(lc_value, precision_digits=precision),
                            'quantity': qty,
                        })
    
    def action_cancel(self):
        """
        Override cancel to also remove location-based allocations.
        """
        # Remove location-based allocations before canceling
        for landed_cost in self:
            landed_cost.location_landed_cost_ids.unlink()
        
        # Call parent cancel
        return super().action_cancel()


class StockValuationAdjustmentLines(models.Model):
    """
    Extension of stock.valuation.adjustment.lines.
    
    Adds reference to location-specific landed cost allocations.
    """
    
    _inherit = 'stock.valuation.adjustment.lines'
    
    location_based_allocations = fields.One2many(
        'stock.valuation.layer.landed.cost',
        'valuation_adjustment_line_id',
        string='Location-based Allocations',
        help='Breakdown of this landed cost by location.',
        readonly=True
    )
    
    def unlink(self):
        """Override unlink to cascade delete location-based allocations."""
        # The CASCADE constraint will handle this automatically,
        # but we explicitly unlink to ensure clean deletion
        for line in self:
            if line.location_based_allocations:
                line.location_based_allocations.unlink()
        return super(StockValuationAdjustmentLines, self).unlink()
