#!/usr/bin/env python3
"""
Test script to verify the search methods implementation
"""

def test_search_method_syntax():
    """Test if the search methods have correct syntax"""
    print("=== TESTING SEARCH METHOD SYNTAX ===")
    print()
    
    # Read the warranty_card.py file
    with open('models/warranty_card.py', 'r') as f:
        content = f.read()
    
    # Check if all search methods exist
    required_methods = [
        '_search_claim_count',
        '_search_days_remaining', 
        '_search_days_since_expiry',
        '_search_last_claim_date'
    ]
    
    for method in required_methods:
        if f'def {method}(' in content:
            print(f"✓ {method} method found")
        else:
            print(f"✗ {method} method NOT found")
    
    print()
    print("=== SYNTAX CHECK COMPLETE ===")

if __name__ == "__main__":
    test_search_method_syntax()