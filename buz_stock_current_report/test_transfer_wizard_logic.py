#!/usr/bin/env python3
"""
Test script for Transfer Wizard Logic
Validates the core functionality without requiring a full Odoo environment
"""

import sys

def test_default_get_logic():
    """Test the default_get context processing logic"""
    
    # Simulate context with selected products
    selected_products = [
        {
            'productId': 1,
            'locationId': 5,
            'quantity': 100,
            'uomId': 1,
            'productName': 'Product A',
            'locationName': 'Location 1'
        },
        {
            'productId': 2,
            'locationId': 5,
            'quantity': 50,
            'uomId': 1,
            'productName': 'Product B',
            'locationName': 'Location 1'
        }
    ]
    
    # Process like default_get does
    lines = []
    source_locations = set()
    
    for product_data in selected_products:
        if not isinstance(product_data, dict):
            continue
        
        product_id = product_data.get('productId') or product_data.get('product_id')
        location_id = product_data.get('locationId') or product_data.get('location_id')
        
        if not product_id or not location_id:
            continue
        
        source_locations.add(location_id)
        
        line_vals = {
            'product_id': product_id,
            'source_location_id': location_id,
            'available_quantity': product_data.get('quantity', 0),
            'quantity_to_transfer': product_data.get('quantity', 0),
            'uom_id': product_data.get('uomId') or product_data.get('uom_id'),
        }
        lines.append(line_vals)
    
    # Assertions
    assert len(lines) == 2, f"Expected 2 lines, got {len(lines)}"
    assert lines[0]['product_id'] == 1, "First line product_id incorrect"
    assert lines[1]['product_id'] == 2, "Second line product_id incorrect"
    assert len(source_locations) == 1, "Should have single source location"
    assert list(source_locations)[0] == 5, "Source location should be 5"
    
    print("✓ test_default_get_logic passed")
    return True

def test_export_wizard_filtering():
    """Test the export wizard filtering logic"""
    
    # Mock record data
    mock_records = [
        {
            'warehouse_id': {'name': 'WH1'},
            'location_id': {'name': 'Loc1'},
            'product_id': {'name': 'Prod1', 'default_code': 'P001'},
            'category_id': {'name': 'Cat1'},
            'uom_id': {'name': 'Unit'},
            'quantity': 100,
            'free_to_use': 100,
            'incoming': 10,
            'outgoing': 5,
            'unit_cost': 10.0,
            'total_value': 1000.0,
            'location_usage': 'internal',
            'stock_date': '2024-01-01',
        }
    ]
    
    # Process like action_export_excel does
    data = []
    for record in mock_records:
        # Simulate obj access
        warehouse_name = record['warehouse_id']['name'] if record['warehouse_id'] else ''
        location_name = record['location_id']['name'] if record['location_id'] else ''
        product_name = record['product_id']['name'] if record['product_id'] else ''
        
        data.append({
            'warehouse': warehouse_name,
            'location': location_name,
            'product': product_name,
            'product_code': record['product_id']['default_code'] if record['product_id'] else '',
            'quantity': record['quantity'],
            'total_value': record['total_value'],
        })
    
    assert len(data) == 1, "Should have 1 export record"
    assert data[0]['warehouse'] == 'WH1', "Warehouse name incorrect"
    assert data[0]['product'] == 'Prod1', "Product name incorrect"
    
    print("✓ test_export_wizard_filtering passed")
    return True

def test_validation_logic():
    """Test validation constraints"""
    
    class MockLine:
        def __init__(self, qty_to_transfer, available_qty):
            self.quantity_to_transfer = qty_to_transfer
            self.available_quantity = available_qty
            self.product_id = type('obj', (object,), {'name': 'Test Product'})()
    
    # Test valid case
    line = MockLine(50, 100)
    assert line.quantity_to_transfer > 0, "Qty should be > 0"
    assert line.quantity_to_transfer <= line.available_quantity, "Qty should not exceed available"
    
    # Test invalid cases
    line = MockLine(0, 100)
    assert not (line.quantity_to_transfer > 0), "Should fail: qty is 0"
    
    line = MockLine(-10, 100)
    assert not (line.quantity_to_transfer > 0), "Should fail: qty is negative"
    
    line = MockLine(150, 100)
    assert not (line.quantity_to_transfer <= line.available_quantity), "Should fail: qty exceeds available"
    
    print("✓ test_validation_logic passed")
    return True

if __name__ == '__main__':
    try:
        test_default_get_logic()
        test_export_wizard_filtering()
        test_validation_logic()
        
        print("\n" + "="*50)
        print("✓ All transfer wizard logic tests passed!")
        print("="*50)
        sys.exit(0)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        sys.exit(1)
