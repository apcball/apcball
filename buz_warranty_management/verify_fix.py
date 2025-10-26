#!/usr/bin/env python3
"""
Verify that the search methods have been fixed with @api.model decorators
"""

def verify_fix():
    """Verify that the search methods have @api.model decorators"""
    
    print("=== Verifying Search Method Fix ===")
    
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
        
        all_fixed = True
        
        for method_name in search_methods:
            # Find the method definition
            method_start = content.find(f'def {method_name}(')
            if method_start == -1:
                print(f"✗ {method_name}: NOT FOUND")
                all_fixed = False
                continue
                
            # Get some context before the method definition
            context_start = max(0, method_start - 200)
            context = content[context_start:method_start + 100]
            
            # Check if it has @api.model decorator
            if '@api.model' in context:
                print(f"✓ {method_name}: Has @api.model decorator - FIXED!")
            else:
                print(f"✗ {method_name}: MISSING @api.model decorator - NOT FIXED")
                all_fixed = False
                
        if all_fixed:
            print("\n🎉 ALL SEARCH METHODS HAVE BEEN FIXED!")
            print("The TypeError: 'Determination requires a callable or method name' should be resolved.")
        else:
            print("\n❌ Some search methods still need fixing.")
                
    except Exception as e:
        print(f"Error during verification: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    verify_fix()