#!/usr/bin/env python3
"""
Debug script to validate the search method issue in warranty_card.py
"""

import sys
import os

# Add the Odoo path to sys.path
sys.path.append('/opt/instance1/odoo17')

def test_search_methods():
    """Test if the search methods are properly callable"""
    
    print("=== Testing Warranty Card Search Methods ===")
    
    # Test 1: Check if search methods exist and are callable
    try:
        # Import the model
        from odoo import api, registry
        
        # Get the database registry
        db_registry = registry.Registry.get('odoo17')
        
        with db_registry.cursor() as cr:
            env = api.Environment(cr, 1, {})  # Admin user
            
            # Get the warranty.card model
            warranty_card_model = env['warranty.card']
            
            print(f"Model: {warranty_card_model}")
            print(f"Model class: {warranty_card_model.__class__}")
            
            # Check if search methods exist
            search_methods = [
                '_search_claim_count',
                '_search_days_remaining', 
                '_search_days_since_expiry',
                '_search_last_claim_date'
            ]
            
            for method_name in search_methods:
                if hasattr(warranty_card_model, method_name):
                    method = getattr(warranty_card_model, method_name)
                    print(f"✓ {method_name}: exists, callable: {callable(method)}")
                    print(f"  Method type: {type(method)}")
                    print(f"  Method: {method}")
                else:
                    print(f"✗ {method_name}: NOT FOUND")
            
            # Test calling one of the search methods
            print("\n=== Testing Search Method Call ===")
            try:
                # This should fail if the method is not properly defined
                result = warranty_card_model._search_claim_count('=', 0)
                print(f"Search method call result: {result}")
            except Exception as e:
                print(f"Search method call failed: {e}")
                print(f"Error type: {type(e)}")
                
    except Exception as e:
        print(f"Error during testing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_search_methods()