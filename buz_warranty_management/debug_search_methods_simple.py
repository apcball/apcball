#!/usr/bin/env python3
"""
Simple debug script to validate the search method issue in warranty_card.py
"""

import sys
import os

def test_search_methods():
    """Test if the search methods are properly defined"""
    
    print("=== Testing Warranty Card Search Methods ===")
    
    # Read the warranty_card.py file and check the search method definitions
    warranty_card_path = '/opt/instance1/odoo17/custom-addons/buz_warranty_management/models/warranty_card.py'
    
    try:
        with open(warranty_card_path, 'r') as f:
            content = f.read()
        
        # Check for search method definitions
        search_methods = [
            '_search_claim_count',
            '_search_days_remaining', 
            '_search_days_since_expiry',
            '_search_last_claim_date'
        ]
        
        for method_name in search_methods:
            # Find the method definition
            method_start = content.find(f'def {method_name}(')
            if method_start == -1:
                print(f"✗ {method_name}: NOT FOUND")
                continue
                
            # Extract the method definition (first few lines)
            method_lines = []
            lines = content[method_start:].split('\n')
            for i, line in enumerate(lines[:10]):  # Get first 10 lines
                method_lines.append(line)
                if line.strip().startswith('return ') or (i > 0 and line.strip() and not line.startswith(' ') and not line.startswith('\t')):
                    break
            
            method_def = '\n'.join(method_lines)
            print(f"\n--- {method_name} ---")
            print(method_def)
            
            # Check if it has @api.model decorator
            if '@api.model' in method_def:
                print(f"✓ {method_name}: Has @api.model decorator")
            else:
                print(f"✗ {method_name}: MISSING @api.model decorator (THIS IS THE ISSUE!)")
                
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_search_methods()