#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test script to verify the duplicate functionality for Internal Consume Request
This script can be run in Odoo shell to test the duplicate functionality
"""

def test_duplicate_request():
    """Test duplicating an internal consume request with lines"""
    # Get a sample request
    request = env['internal.consume.request'].search([], limit=1)
    
    if not request:
        print("No Internal Consume Request found. Please create one first.")
        return
    
    print(f"Original Request: {request.name}")
    print(f"Original State: {request.state}")
    print(f"Original Lines Count: {len(request.line_ids)}")
    
    # Test the duplicate action
    try:
        # Call the duplicate action
        action = request.action_duplicate_request()
        
        # Get the new request ID from the action
        new_request_id = action.get('res_id')
        new_request = env['internal.consume.request'].browse(new_request_id)
        
        print(f"\nDuplicated Request: {new_request.name}")
        print(f"Duplicated State: {new_request.state}")
        print(f"Duplicated Lines Count: {len(new_request.line_ids)}")
        
        # Verify all lines were copied
        if len(request.line_ids) == len(new_request.line_ids):
            print("\n✅ SUCCESS: All lines were duplicated correctly!")
            
            # Check line details
            for i, (orig_line, dup_line) in enumerate(zip(request.line_ids, new_request.line_ids)):
                if (orig_line.product_id == dup_line.product_id and 
                    orig_line.qty_requested == dup_line.qty_requested and
                    orig_line.analytic_distribution == dup_line.analytic_distribution):
                    print(f"  Line {i+1}: ✅ {orig_line.product_id.name} - Qty: {orig_line.qty_requested}")
                else:
                    print(f"  Line {i+1}: ❌ Mismatch detected")
        else:
            print(f"\n❌ ERROR: Line count mismatch. Original: {len(request.line_ids)}, Duplicated: {len(new_request.line_ids)}")
            
    except Exception as e:
        print(f"\n❌ ERROR: Failed to duplicate request: {str(e)}")

# Uncomment the line below to run this test in Odoo shell
# test_duplicate_request()