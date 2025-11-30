# -*- coding: utf-8 -*-
"""
Landed Cost by Warehouse Model

This module tracks landed costs on a per-warehouse basis to ensure that when
goods are transferred between warehouses, the associated landed costs are also
properly allocated to the new warehouse.

Landed cost is the additional cost added to the purchase of goods, such as
freight, insurance, customs, etc. This extension ensures that when inventory
is transferred internally between warehouses, the landed cost portion is also
transferred proportionally.
"""

from odoo import models, fields, api
from odoo.tools import float_compare, float_round


class StockValuationLayerLandedCost(models.Model):
    """
    Tracks landed cost allocation per warehouse for stock valuation layers.
    
    Each layer can have associated landed costs that were applied to incoming
    stock. When inventory is transferred internally between warehouses, we need to allocate the
    landed cost proportionally to the receiving warehouse.
    
    This model maintains the relationship between:
    - stock.valuation.layer (the inventory layer)
    - stock.warehouse (the warehouse)
    - landed cost amount
    """
    
    _name = 'stock.valuation.layer.landed.cost'
    _description = 'Landed Cost by Warehouse'
    _rec_name = 'valuation_layer_id'
    
    # Allow deletion even when referenced
    _sql_constraints = []
    
    valuation_layer_id = fields.Many2one(
        'stock.valuation.layer',
        string='Valuation Layer',
        required=False,
        ondelete='set null',
        help='The stock valuation layer this landed cost applies to.'
    )
    
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        required=False,
        index=True,
        help='The warehouse where this landed cost is applicable.'
    )
    
    def init(self):
        """Create composite indexes for landed cost queries."""
        # Composite index for landed cost lookups by layer and warehouse
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS svl_landed_cost_layer_wh_idx
            ON stock_valuation_layer_landed_cost (valuation_layer_id, warehouse_id)
        """)
        
        # Index for product and warehouse landed cost aggregations
        self.env.cr.execute("""
            CREATE INDEX IF NOT EXISTS svl_landed_cost_product_wh_idx
            ON stock_valuation_layer_landed_cost (warehouse_id, landed_cost_value)
            WHERE landed_cost_value > 0
        """)
    
    landed_cost_id = fields.Many2one(
        'stock.landed.cost',
        string='Landed Cost',
        ondelete='set null',
        help='The source landed cost document.'
    )
    
    valuation_adjustment_line_id = fields.Many2one(
        'stock.valuation.adjustment.lines',
        string='Valuation Adjustment Line',
        ondelete='cascade',
        help='Reference to the valuation adjustment line from landed cost.'
    )
    
    landed_cost_value = fields.Float(
        string='Landed Cost Value',
        digits='Product Price',
        help='The amount of landed cost allocated to this location for this layer.'
    )
    
    quantity = fields.Float(
        string='Quantity',
        digits='Product Unit of Measure',
        help='Quantity of product this landed cost covers.'
    )
    
    unit_landed_cost = fields.Float(
        string='Unit Landed Cost',
        digits='Product Price',
        compute='_compute_unit_landed_cost',
        help='Landed cost per unit: landed_cost_value / quantity'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        related='valuation_layer_id.product_id',
        readonly=True,
        store=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='valuation_layer_id.company_id',
        readonly=True,
        store=True
    )
    
    @api.depends('landed_cost_value', 'quantity')
    def _compute_unit_landed_cost(self):
        """Compute landed cost per unit."""
        precision = self.env['decimal.precision'].precision_get('Product Price')
        for record in self:
            if record.quantity and float_compare(
                record.quantity, 0, precision_digits=precision
            ) > 0:
                record.unit_landed_cost = float_round(
                    record.landed_cost_value / record.quantity,
                    precision_digits=precision
                )
            else:
                record.unit_landed_cost = 0.0
    
    @api.model
    def get_landed_cost_for_layer_at_warehouse(self, valuation_layer_id, warehouse_id):
        """
        Get total landed cost for a valuation layer at a specific warehouse.
        
        Args:
            valuation_layer_id: ID of stock.valuation.layer
            warehouse_id: ID of stock.warehouse
            
        Returns:
            float: Total landed cost value
        """
        record = self.search([
            ('valuation_layer_id', '=', valuation_layer_id),
            ('warehouse_id', '=', warehouse_id),
        ], limit=1)
        
        return record.landed_cost_value if record else 0.0
    
    @api.model
    def get_unit_landed_cost_for_layer_at_warehouse(self, valuation_layer_id, warehouse_id):
        """
        Get unit landed cost for a valuation layer at a specific warehouse.
        
        Args:
            valuation_layer_id: ID of stock.valuation.layer
            warehouse_id: ID of stock.warehouse
            
        Returns:
            float: Landed cost per unit
        """
        record = self.search([
            ('valuation_layer_id', '=', valuation_layer_id),
            ('warehouse_id', '=', warehouse_id),
        ], limit=1)
        
        return record.unit_landed_cost if record else 0.0
    
    def unlink(self):
        """Override unlink to handle foreign key constraints properly."""
        # CASCADE constraint will handle deletion automatically
        # No need to clear fields manually
        return super(StockValuationLayerLandedCost, self).unlink()
    
    def write(self, vals):
        """Override write to ensure data consistency."""
        # Ensure we can write to these fields
        return super().write(vals)


class StockValuationLayerLandedCostAllocation(models.Model):
    """
    Tracks the allocation of landed costs during inter-warehouse transfers.
    
    When inventory is transferred between warehouses, landed costs need to be
    allocated proportionally. This model tracks:
    - Source warehouse landed cost (being reduced)
    - Destination warehouse landed cost (being added)
    - The proportion transferred
    
    This creates an audit trail for cost allocation during inter-warehouse transfers.
    """
    
    _name = 'stock.landed.cost.allocation'
    _description = 'Landed Cost Allocation History'
    _rec_name = 'move_id'
    _order = 'create_date DESC'
    
    move_id = fields.Many2one(
        'stock.move',
        string='Stock Move',
        required=True,
        ondelete='cascade',
        help='The stock move that triggered this allocation.'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        related='move_id.product_id',
        readonly=True,
        store=True
    )
    
    source_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Source Warehouse',
        compute='_compute_warehouses',
        readonly=True,
        store=True
    )
    
    destination_warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Destination Warehouse',
        compute='_compute_warehouses',
        readonly=True,
        store=True
    )
    
    @api.depends('move_id.location_id', 'move_id.location_dest_id')
    def _compute_warehouses(self):
        """Compute source and destination warehouses from move locations."""
        for record in self:
            if record.move_id:
                if record.move_id.location_id:
                    record.source_warehouse_id = record.move_id.location_id.warehouse_id
                else:
                    record.source_warehouse_id = False
                
                if record.move_id.location_dest_id:
                    record.destination_warehouse_id = record.move_id.location_dest_id.warehouse_id
                else:
                    record.destination_warehouse_id = False
            else:
                record.source_warehouse_id = False
                record.destination_warehouse_id = False
    
    quantity_transferred = fields.Float(
        string='Quantity Transferred',
        digits='Product Unit of Measure',
        help='Amount of product transferred.'
    )
    
    source_layer_landed_cost_before = fields.Float(
        string='Source Warehouse LC Before',
        digits='Product Price',
        help='Landed cost value at source warehouse before transfer.'
    )
    
    source_layer_landed_cost_after = fields.Float(
        string='Source Warehouse LC After',
        digits='Product Price',
        help='Landed cost value at source warehouse after transfer.'
    )
    
    destination_layer_landed_cost_before = fields.Float(
        string='Destination Warehouse LC Before',
        digits='Product Price',
        help='Landed cost value at destination warehouse before transfer.'
    )
    
    destination_layer_landed_cost_after = fields.Float(
        string='Destination Warehouse LC After',
        digits='Product Price',
        help='Landed cost value at destination warehouse after transfer.'
    )
    
    landed_cost_transferred = fields.Float(
        string='Landed Cost Transferred',
        digits='Product Price',
        help='Amount of landed cost transferred from source to destination.'
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='move_id.company_id',
        readonly=True,
        store=True
    )
    
    notes = fields.Text(
        string='Notes',
        help='Additional notes about this allocation.'
    )
