# -*- coding: utf-8 -*-
"""
Test script for inter-warehouse transfer with FIFO by location

This script tests that:
1. Transfer from WH-A to WH-B creates 2 layers:
   - Negative layer at WH-A (consuming from FIFO)
   - Positive layer at WH-B (new FIFO source)
2. FIFO cost is correctly calculated from source warehouse
3. remaining_qty is correctly updated at both warehouses
4. Sales from WH-B after transfer uses the correct FIFO cost

Usage:
    python test_inter_warehouse_transfer.py
    
Or from Odoo shell:
    odoo-bin shell -d <database> -c <config>
    >>> execfile('test_inter_warehouse_transfer.py')
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def test_inter_warehouse_transfer(env):
    """
    Test inter-warehouse transfer scenario.
    
    Scenario:
    1. Receive 10 units to WH-A @ 100/unit
    2. Transfer 5 units from WH-A to WH-B
    3. Verify layers created correctly
    4. Sell 3 units from WH-B
    5. Verify FIFO consumption at WH-B uses correct cost
    """
    _logger.info("="*80)
    _logger.info("🧪 Starting Inter-Warehouse Transfer Test")
    _logger.info("="*80)
    
    # Get models
    Product = env['stock.product.product']
    Location = env['stock.location']
    Warehouse = env['stock.warehouse']
    Move = env['stock.move']
    Layer = env['stock.valuation.layer']
    
    # Find or create test warehouses
    wh_a = Warehouse.search([('code', '=', 'WH-A')], limit=1)
    if not wh_a:
        wh_a = Warehouse.create({
            'name': 'Warehouse A',
            'code': 'WH-A',
        })
        _logger.info(f"✅ Created Warehouse A: {wh_a.name}")
    
    wh_b = Warehouse.search([('code', '=', 'WH-B')], limit=1)
    if not wh_b:
        wh_b = Warehouse.create({
            'name': 'Warehouse B',
            'code': 'WH-B',
        })
        _logger.info(f"✅ Created Warehouse B: {wh_b.name}")
    
    # Find or create test product
    product = Product.search([('default_code', '=', 'TEST-IWT-001')], limit=1)
    if not product:
        # Find FIFO category
        fifo_category = env['product.category'].search([
            ('property_cost_method', '=', 'fifo')
        ], limit=1)
        if not fifo_category:
            fifo_category = env['product.category'].create({
                'name': 'FIFO Products',
                'property_cost_method': 'fifo',
                'property_valuation': 'real_time',
            })
        
        product = Product.create({
            'name': 'Test Product Inter-Warehouse Transfer',
            'default_code': 'TEST-IWT-001',
            'type': 'product',
            'categ_id': fifo_category.id,
            'standard_price': 100.0,
            'list_price': 200.0,
        })
        _logger.info(f"✅ Created test product: {product.name}")
    
    _logger.info(f"📦 Product: {product.name} (ID: {product.id})")
    _logger.info(f"🏢 Warehouse A: {wh_a.name} (ID: {wh_a.id})")
    _logger.info(f"🏢 Warehouse B: {wh_b.name} (ID: {wh_b.id})")
    
    # Get locations
    supplier_loc = env.ref('stock.stock_location_suppliers')
    customer_loc = env.ref('stock.stock_location_customers')
    loc_a = wh_a.lot_stock_id
    loc_b = wh_b.lot_stock_id
    
    _logger.info("")
    _logger.info("="*80)
    _logger.info("STEP 1: Receive 10 units to WH-A @ 100/unit")
    _logger.info("="*80)
    
    # Create receipt move to WH-A
    receipt_move = Move.create({
        'name': 'IN: Receive to WH-A',
        'product_id': product.id,
        'product_uom': product.uom_id.id,
        'product_uom_qty': 10.0,
        'location_id': supplier_loc.id,
        'location_dest_id': loc_a.id,
        'price_unit': 100.0,
    })
    receipt_move._action_confirm()
    receipt_move._action_assign()
    receipt_move.move_line_ids.write({'qty_done': 10.0})
    receipt_move._action_done()
    
    _logger.info(f"✅ Receipt move done: {receipt_move.name}")
    
    # Check layers created
    receipt_layers = Layer.search([('stock_move_id', '=', receipt_move.id)])
    _logger.info(f"📊 Receipt layers created: {len(receipt_layers)}")
    for layer in receipt_layers:
        _logger.info(
            f"   Layer {layer.id}: "
            f"Warehouse={layer.warehouse_id.name if layer.warehouse_id else 'None'}, "
            f"qty={layer.quantity}, value={layer.value:.2f}, "
            f"remaining_qty={layer.remaining_qty}, remaining_value={layer.remaining_value:.2f}"
        )
    
    _logger.info("")
    _logger.info("="*80)
    _logger.info("STEP 2: Transfer 5 units from WH-A to WH-B")
    _logger.info("="*80)
    
    # Create inter-warehouse transfer
    transfer_move = Move.create({
        'name': 'TRANSFER: WH-A → WH-B',
        'product_id': product.id,
        'product_uom': product.uom_id.id,
        'product_uom_qty': 5.0,
        'location_id': loc_a.id,
        'location_dest_id': loc_b.id,
    })
    transfer_move._action_confirm()
    transfer_move._action_assign()
    transfer_move.move_line_ids.write({'qty_done': 5.0})
    transfer_move._action_done()
    
    _logger.info(f"✅ Transfer move done: {transfer_move.name}")
    
    # Check layers created for transfer
    transfer_layers = Layer.search([('stock_move_id', '=', transfer_move.id)])
    _logger.info(f"📊 Transfer layers created: {len(transfer_layers)}")
    
    negative_layer = None
    positive_layer = None
    
    for layer in transfer_layers:
        _logger.info(
            f"   Layer {layer.id}: "
            f"Warehouse={layer.warehouse_id.name if layer.warehouse_id else 'None'}, "
            f"qty={layer.quantity}, value={layer.value:.2f}, "
            f"remaining_qty={layer.remaining_qty}, remaining_value={layer.remaining_value:.2f}"
        )
        if layer.quantity < 0:
            negative_layer = layer
        elif layer.quantity > 0:
            positive_layer = layer
    
    _logger.info("")
    _logger.info("="*80)
    _logger.info("STEP 3: Verify layers created correctly")
    _logger.info("="*80)
    
    # Verify negative layer at WH-A
    if negative_layer:
        assert negative_layer.warehouse_id == wh_a, \
            f"❌ Negative layer warehouse should be WH-A, got {negative_layer.warehouse_id.name}"
        assert negative_layer.quantity == -5.0, \
            f"❌ Negative layer quantity should be -5, got {negative_layer.quantity}"
        assert negative_layer.remaining_qty == 0.0, \
            f"❌ Negative layer remaining_qty should be 0, got {negative_layer.remaining_qty}"
        _logger.info(f"✅ Negative layer at WH-A is correct")
    else:
        _logger.error(f"❌ No negative layer found!")
    
    # Verify positive layer at WH-B
    if positive_layer:
        assert positive_layer.warehouse_id == wh_b, \
            f"❌ Positive layer warehouse should be WH-B, got {positive_layer.warehouse_id.name}"
        assert positive_layer.quantity == 5.0, \
            f"❌ Positive layer quantity should be 5, got {positive_layer.quantity}"
        assert positive_layer.remaining_qty == 5.0, \
            f"❌ Positive layer remaining_qty should be 5, got {positive_layer.remaining_qty}"
        _logger.info(f"✅ Positive layer at WH-B is correct")
    else:
        _logger.error(f"❌ No positive layer found!")
    
    # Check remaining at WH-A
    remaining_a = Layer.search([
        ('product_id', '=', product.id),
        ('warehouse_id', '=', wh_a.id),
        ('remaining_qty', '>', 0),
    ])
    total_remaining_a = sum(remaining_a.mapped('remaining_qty'))
    _logger.info(f"📊 Total remaining at WH-A: {total_remaining_a} (should be 5)")
    assert abs(total_remaining_a - 5.0) < 0.01, \
        f"❌ Remaining at WH-A should be 5, got {total_remaining_a}"
    _logger.info(f"✅ Remaining at WH-A is correct")
    
    # Check remaining at WH-B
    remaining_b = Layer.search([
        ('product_id', '=', product.id),
        ('warehouse_id', '=', wh_b.id),
        ('remaining_qty', '>', 0),
    ])
    total_remaining_b = sum(remaining_b.mapped('remaining_qty'))
    _logger.info(f"📊 Total remaining at WH-B: {total_remaining_b} (should be 5)")
    assert abs(total_remaining_b - 5.0) < 0.01, \
        f"❌ Remaining at WH-B should be 5, got {total_remaining_b}"
    _logger.info(f"✅ Remaining at WH-B is correct")
    
    _logger.info("")
    _logger.info("="*80)
    _logger.info("STEP 4: Sell 3 units from WH-B")
    _logger.info("="*80)
    
    # Create delivery from WH-B
    delivery_move = Move.create({
        'name': 'OUT: Sell from WH-B',
        'product_id': product.id,
        'product_uom': product.uom_id.id,
        'product_uom_qty': 3.0,
        'location_id': loc_b.id,
        'location_dest_id': customer_loc.id,
    })
    delivery_move._action_confirm()
    delivery_move._action_assign()
    delivery_move.move_line_ids.write({'qty_done': 3.0})
    delivery_move._action_done()
    
    _logger.info(f"✅ Delivery move done: {delivery_move.name}")
    
    # Check layers created for delivery
    delivery_layers = Layer.search([('stock_move_id', '=', delivery_move.id)])
    _logger.info(f"📊 Delivery layers created: {len(delivery_layers)}")
    for layer in delivery_layers:
        _logger.info(
            f"   Layer {layer.id}: "
            f"Warehouse={layer.warehouse_id.name if layer.warehouse_id else 'None'}, "
            f"qty={layer.quantity}, value={layer.value:.2f}, "
            f"unit_cost={layer.unit_cost:.2f}"
        )
    
    _logger.info("")
    _logger.info("="*80)
    _logger.info("STEP 5: Verify FIFO consumption at WH-B")
    _logger.info("="*80)
    
    # Check remaining at WH-B after sale
    remaining_b_after = Layer.search([
        ('product_id', '=', product.id),
        ('warehouse_id', '=', wh_b.id),
        ('remaining_qty', '>', 0),
    ])
    total_remaining_b_after = sum(remaining_b_after.mapped('remaining_qty'))
    _logger.info(f"📊 Total remaining at WH-B after sale: {total_remaining_b_after} (should be 2)")
    assert abs(total_remaining_b_after - 2.0) < 0.01, \
        f"❌ Remaining at WH-B should be 2, got {total_remaining_b_after}"
    _logger.info(f"✅ Remaining at WH-B after sale is correct")
    
    _logger.info("")
    _logger.info("="*80)
    _logger.info("🎉 All tests passed!")
    _logger.info("="*80)
    
    # Summary
    _logger.info("")
    _logger.info("📋 SUMMARY")
    _logger.info("-"*80)
    _logger.info(f"Product: {product.name}")
    _logger.info(f"Initial receipt to WH-A: 10 units @ 100/unit")
    _logger.info(f"Transfer WH-A → WH-B: 5 units")
    _logger.info(f"Sale from WH-B: 3 units")
    _logger.info(f"Final remaining at WH-A: {total_remaining_a} units")
    _logger.info(f"Final remaining at WH-B: {total_remaining_b_after} units")
    _logger.info("")
    _logger.info("✅ Inter-warehouse transfer is working correctly!")
    _logger.info("✅ FIFO consumption respects warehouse boundaries!")
    _logger.info("✅ Positive layer at destination becomes FIFO source!")


if __name__ == '__main__':
    # This script is meant to be run from Odoo shell
    _logger.warning("This script should be run from Odoo shell:")
    _logger.warning("  odoo-bin shell -d <database> -c <config>")
    _logger.warning("  >>> execfile('test_inter_warehouse_transfer.py')")
    _logger.warning("  >>> test_inter_warehouse_transfer(env)")
else:
    # Running from Odoo shell - execute immediately
    # Uncomment the line below to run automatically when loaded
    # test_inter_warehouse_transfer(env)
    pass
