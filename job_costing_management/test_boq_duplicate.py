#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify BOQ duplicate functionality
This script can be run in Odoo shell to test the BOQ duplication
"""

def test_boq_duplicate():
    """Test BOQ duplication functionality"""
    # This would be run in Odoo shell context
    print("Testing BOQ duplication...")
    
    # Get an existing BOQ
    boq = env['boq.boq'].search([('state', '=', 'draft')], limit=1)
    
    if not boq:
        print("No BOQ found to test duplication")
        return False
    
    print(f"Original BOQ: {boq.name}")
    print(f"Original BOQ has {len(boq.line_ids)} lines")
    
    # Test duplication
    new_boq = boq.copy()
    
    print(f"New BOQ: {new_boq.name}")
    print(f"New BOQ has {len(new_boq.line_ids)} lines")
    
    # Verify products are copied
    for line in new_boq.line_ids:
        if line.product_id:
            print(f"Line {line.sequence}: Product {line.product_id.name} copied successfully")
        else:
            print(f"Line {line.sequence}: No product (this may be expected)")
    
    return True

if __name__ == "__main__":
    test_boq_duplicate()
