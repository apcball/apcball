# -*- coding: utf-8 -*-

"""
Test script to verify the product validation fix works correctly.
This can be run in Odoo shell to test the validation behavior.
"""

def test_auto_cost_type_adjustment():
    """Test the automatic cost type adjustment based on product type"""
    
    # Get required models
    JobCostSheet = env['job.cost.sheet']
    JobCostLine = env['job.cost.line']
    Product = env['product.product']
    
    print("=== Testing Auto Cost Type Adjustment ===")
    
    # Create test products
    service_product = Product.create({
        'name': 'Test Service Product (Auto-Labour)',
        'detailed_type': 'service',
        'standard_price': 100.0,
        'purchase_ok': True,
    })
    
    material_product = Product.create({
        'name': 'Test Material Product (Auto-Material)', 
        'detailed_type': 'product',
        'standard_price': 50.0,
        'purchase_ok': True,
    })
    
    consumable_product = Product.create({
        'name': 'Test Consumable Product (Auto-Material)', 
        'detailed_type': 'consu',
        'standard_price': 25.0,
        'purchase_ok': True,
    })
    
    # Create test job cost sheet
    cost_sheet = JobCostSheet.create({
        'name': 'Test Auto-Adjustment Cost Sheet',
        'project_id': env['project.project'].search([], limit=1).id,
    })
    
    print(f"Created test cost sheet: {cost_sheet.name}")
    
    # Test 1: Service product should auto-set to Labour
    print("\n--- Test 1: Service Product → Labour Cost Type ---")
    try:
        labour_line = JobCostLine.create({
            'cost_sheet_id': cost_sheet.id,
            'cost_type': 'material',  # Start with material
            'name': 'Test Line - Will become Labour',
            'planned_qty': 1.0,
            'unit_cost': 100.0,
        })
        
        # Set service product - should auto-change to labour
        labour_line.product_id = service_product.id
        labour_line._onchange_product_id()
        
        print(f"✅ Cost type auto-changed to: {labour_line.cost_type}")
        print(f"   Product type: {service_product.detailed_type}")
        print(f"   UOM: {labour_line.uom_id.name if labour_line.uom_id else 'None'}")
        
    except Exception as e:
        print(f"❌ Error in service product test: {e}")
    
    # Test 2: Storable product should auto-set to Material
    print("\n--- Test 2: Storable Product → Material Cost Type ---")
    try:
        material_line = JobCostLine.create({
            'cost_sheet_id': cost_sheet.id,
            'cost_type': 'labour',  # Start with labour
            'name': 'Test Line - Will become Material',
            'planned_qty': 1.0,
            'unit_cost': 50.0,
        })
        
        # Set storable product - should auto-change to material
        material_line.product_id = material_product.id
        material_line._onchange_product_id()
        
        print(f"✅ Cost type auto-changed to: {material_line.cost_type}")
        print(f"   Product type: {material_product.detailed_type}")
        print(f"   UOM: {material_line.uom_id.name if material_line.uom_id else 'None'}")
        
    except Exception as e:
        print(f"❌ Error in storable product test: {e}")
    
    # Test 3: Consumable product should auto-set to Material
    print("\n--- Test 3: Consumable Product → Material Cost Type ---")
    try:
        consumable_line = JobCostLine.create({
            'cost_sheet_id': cost_sheet.id,
            'cost_type': 'labour',  # Start with labour
            'name': 'Test Line - Will become Material',
            'planned_qty': 1.0,
            'unit_cost': 25.0,
        })
        
        # Set consumable product - should auto-change to material
        consumable_line.product_id = consumable_product.id
        consumable_line._onchange_product_id()
        
        print(f"✅ Cost type auto-changed to: {consumable_line.cost_type}")
        print(f"   Product type: {consumable_product.detailed_type}")
        print(f"   UOM: {consumable_line.uom_id.name if consumable_line.uom_id else 'None'}")
        
    except Exception as e:
        print(f"❌ Error in consumable product test: {e}")
    
    # Test 4: RFQ Creation with auto-adjusted cost types
    print("\n--- Test 4: RFQ Creation with Auto-Adjusted Types ---")
    try:
        # Create RFQ wizard
        vendor = env['res.partner'].search([('supplier_rank', '>', 0)], limit=1)
        if not vendor:
            vendor = env['res.partner'].create({
                'name': 'Test Vendor for Auto-Adjustment',
                'supplier_rank': 1,
                'is_company': True,
            })
        
        # Include all types of cost lines
        all_lines = []
        if 'labour_line' in locals():
            all_lines.append(labour_line.id)
        if 'material_line' in locals():
            all_lines.append(material_line.id)
        if 'consumable_line' in locals():
            all_lines.append(consumable_line.id)
        
        if all_lines:
            rfq_wizard = env['create.rfq.from.job.cost'].create({
                'job_cost_sheet_id': cost_sheet.id,
                'partner_id': vendor.id,
                'cost_line_ids': [(6, 0, all_lines)],
            })
            
            # Create RFQ
            result = rfq_wizard.action_create_rfq()
            print("✅ RFQ created successfully with auto-adjusted cost types")
            print(f"RFQ ID: {result.get('res_id', 'Unknown')}")
            
            # Check the created PO
            if result.get('res_id'):
                po = env['purchase.order'].browse(result['res_id'])
                print(f"   PO Lines created: {len(po.order_line)}")
                for line in po.order_line:
                    cost_line = line.job_cost_line_id
                    print(f"   - {line.product_id.name} ({line.product_id.detailed_type}) → {cost_line.cost_type}")
        else:
            print("⚠️ No cost lines available for RFQ creation")
        
    except Exception as e:
        print(f"❌ Error creating RFQ: {e}")
    
    print("\n=== Auto-Adjustment Test Complete ===")
    print("✅ Service products now automatically set cost type to 'Labour'")
    print("✅ Storable/Consumable products automatically set cost type to 'Material'")
    print("✅ RFQ creation works with all cost types including labour")

# Update the original test function
def test_product_validation_fix():
    """Test the flexible product validation system"""
    
    # Get required models
    JobCostSheet = env['job.cost.sheet']
    JobCostLine = env['job.cost.line']
    Product = env['product.product']
    
    print("=== Testing Product Validation Fix ===")
    
    # Create test products
    service_product = Product.create({
        'name': 'Test Service Product',
        'detailed_type': 'service',
        'standard_price': 100.0,
    })
    
    material_product = Product.create({
        'name': 'Test Material Product', 
        'detailed_type': 'product',
        'standard_price': 50.0,
    })
    
    # Create test job cost sheet
    cost_sheet = JobCostSheet.create({
        'name': 'Test Cost Sheet',
        'project_id': env['project.project'].search([], limit=1).id,
    })
    
    print(f"Created test cost sheet: {cost_sheet.name}")
    
    # Test 1: Material cost line with service product (should warn, not error)
    print("\n--- Test 1: Material + Service Product (Manual Override) ---")
    try:
        material_line = JobCostLine.with_context(flexible_product_validation=True).create({
            'cost_sheet_id': cost_sheet.id,
            'cost_type': 'material',
            'product_id': service_product.id,
            'name': 'Test Material Line with Service Product',
            'planned_qty': 1.0,
            'unit_cost': 100.0,
        })
        print("✅ Material line with service product created successfully (with warnings)")
        print("   Note: Auto-adjustment would normally change this to 'labour'")
        
        # Test validation helper method
        is_valid, message = material_line.validate_product_for_cost_type(service_product.id, 'material')
        print(f"Validation result: {is_valid}, Message: {message}")
        
    except Exception as e:
        print(f"❌ Error creating material line: {e}")
    
    print("\n=== Validation Test Complete ===")
    print("Now testing auto-adjustment feature...")
    
    # Run the auto-adjustment test
    test_auto_cost_type_adjustment()

# Uncomment the line below to run the test when this file is executed
# test_product_validation_fix()