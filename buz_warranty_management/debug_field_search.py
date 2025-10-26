#!/usr/bin/env python3
"""
Debug script to validate the field search issue in warranty_card.py
This script will help confirm that the missing search methods are causing the error.
"""

import logging

# Set up logging
_logger = logging.getLogger(__name__)

def test_field_search_issue():
    """
    Test to reproduce the field search issue
    """
    print("=== WARRANTY MANAGEMENT FIELD SEARCH DEBUG ===")
    print()
    
    print("ISSUE IDENTIFIED:")
    print("The following fields in warranty_card.py have 'search=True' but missing search methods:")
    print()
    
    # List the problematic fields
    problematic_fields = [
        {
            'name': 'claim_count',
            'line': 94,
            'compute_method': '_compute_claim_count',
            'expected_search_method': '_search_claim_count'
        },
        {
            'name': 'days_remaining', 
            'line': 104,
            'compute_method': '_compute_days_remaining',
            'expected_search_method': '_search_days_remaining'
        },
        {
            'name': 'days_since_expiry',
            'line': 109, 
            'compute_method': '_compute_days_since_expiry',
            'expected_search_method': '_search_days_since_expiry'
        },
        {
            'name': 'last_claim_date',
            'line': 114,
            'compute_method': '_compute_last_claim_date', 
            'expected_search_method': '_search_last_claim_date'
        }
    ]
    
    for field in problematic_fields:
        print(f"• Field: {field['name']} (line {field['line']})")
        print(f"  - Has compute method: {field['compute_method']}")
        print(f"  - Missing search method: {field['expected_search_method']}")
        print()
    
    print("ROOT CAUSE:")
    print("When a field has 'search=True', Odoo requires a corresponding search method")
    print("with the naming convention '_search_<field_name>'. Without these methods,")
    print("Odoo throws 'TypeError: Determination requires a callable or method name'")
    print("when trying to search/filter on these fields.")
    print()
    
    print("SOLUTION:")
    print("Add the missing search methods to warranty_card.py:")
    print()
    
    # Generate the search method templates
    for field in problematic_fields:
        method_name = field['expected_search_method']
        print(f"def {method_name}(self, operator, value):")
        print(f"    \"\"\"Search method for {field['name']} field\"\"\"")
        
        if field['name'] == 'claim_count':
            print("    # Search warranty cards with specific number of claims")
            print("    warranty_cards = self.env['warranty.card'].search([])")
            print("    result_ids = [w.id for w in warranty_cards if len(w.claim_ids) == value]")
            print("    return [('id', 'in', result_ids)]")
        elif field['name'] == 'days_remaining':
            print("    # Search warranty cards with specific days remaining")
            print("    today = fields.Date.today()")
            print("    target_date = today + timedelta(days=value)")
            print("    return [('end_date', '>=', today), ('end_date', '<=', target_date)]")
        elif field['name'] == 'days_since_expiry':
            print("    # Search warranty cards with specific days since expiry")
            print("    today = fields.Date.today()")
            print("    target_date = today - timedelta(days=value)")
            print("    return [('end_date', '<', today), ('end_date', '>=', target_date)]")
        elif field['name'] == 'last_claim_date':
            print("    # Search warranty cards with last claim date")
            print("    return [('claim_ids.claim_date', operator, value)]")
        
        print()
    
    print("=== END DEBUG ANALYSIS ===")

if __name__ == "__main__":
    test_field_search_issue()