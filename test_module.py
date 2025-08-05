#!/usr/bin/env python3
import sys
import os

# Add the custom-addons directory to Python path
sys.path.insert(0, '/opt/instance1/odoo17/custom-addons')

try:
    # Test importing our module components
    print("Testing module imports...")
    
    # Test models
    from buz_inventory_valuation_report.models import inventory_valuation_report
    print("✓ Models import successful")
    
    # Test wizard
    from buz_inventory_valuation_report.wizard import inventory_valuation_wizard
    print("✓ Wizard import successful")
    
    # Test reports
    from buz_inventory_valuation_report.reports import inventory_valuation_pdf_report
    from buz_inventory_valuation_report.reports import inventory_valuation_xlsx_report
    print("✓ Reports import successful")
    
    print("\n✅ All module components import successfully!")
    
except Exception as e:
    print(f"❌ Import error: {e}")
    import traceback
    traceback.print_exc()
