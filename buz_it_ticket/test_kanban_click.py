#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify kanban click functionality
This script checks that the kanban view has the correct classes and fields
"""

import os
import sys

def check_kanban_view():
    """Check if the kanban view has the required modifications"""
    kanban_file = os.path.join(os.path.dirname(__file__), 'views', 'it_ticket_kanban.xml')
    
    with open(kanban_file, 'r') as f:
        content = f.read()
    
    # Check for oe_kanban_global_click class
    if 'oe_kanban_global_click' in content:
        print("✓ Kanban view has oe_kanban_global_click class")
    else:
        print("✗ Kanban view missing oe_kanban_global_click class")
        return False
    
    # Check for conditional SLA styling
    if 'oe_kanban_color_4' in content:
        print("✓ Kanban view has SLA breach styling")
    else:
        print("✗ Kanban view missing SLA breach styling")
        return False
    
    # Check for category field
    if 'field name="category"' in content:
        print("✓ Kanban view has category field")
    else:
        print("✗ Kanban view missing category field")
        return False
    
    return True

def check_js_modifications():
    """Check if JavaScript has the required modifications"""
    js_file = os.path.join(os.path.dirname(__file__), 'static', 'src', 'js', 'it_ticket.js')
    
    with open(js_file, 'r') as f:
        content = f.read()
    
    # Check for patch import
    if 'patch' in content and 'KanbanRecord' in content:
        print("✓ JavaScript has patch for KanbanRecord")
    else:
        print("✗ JavaScript missing patch for KanbanRecord")
        return False
    
    # Check for openRecord method
    if 'openRecord()' in content:
        print("✓ JavaScript has openRecord method")
    else:
        print("✗ JavaScript missing openRecord method")
        return False
    
    # Check for form view IDs
    if 'view_it_ticket_issue_form' in content:
        print("✓ JavaScript references issue form view")
    else:
        print("✗ JavaScript missing issue form view reference")
        return False
    
    if 'view_it_ticket_access_form' in content:
        print("✓ JavaScript references access form view")
    else:
        print("✗ JavaScript missing access form view reference")
        return False
    
    if 'view_it_ticket_purchase_form' in content:
        print("✓ JavaScript references purchase form view")
    else:
        print("✗ JavaScript missing purchase form view reference")
        return False
    
    return True

def check_model_modifications():
    """Check if model has the required modifications"""
    model_file = os.path.join(os.path.dirname(__file__), 'models', 'it_ticket.py')
    
    with open(model_file, 'r') as f:
        content = f.read()
    
    # Check for get_form_view_id method
    if 'def get_form_view_id(self):' in content:
        print("✓ Model has get_form_view_id method")
    else:
        print("✗ Model missing get_form_view_id method")
        return False
    
    return True

def main():
    """Run all checks"""
    print("Testing IT Ticket Kanban Click Implementation")
    print("=" * 50)
    
    all_passed = True
    
    print("\n1. Checking Kanban View:")
    if not check_kanban_view():
        all_passed = False
    
    print("\n2. Checking JavaScript Modifications:")
    if not check_js_modifications():
        all_passed = False
    
    print("\n3. Checking Model Modifications:")
    if not check_model_modifications():
        all_passed = False
    
    print("\n" + "=" * 50)
    if all_passed:
        print("✓ All checks passed! The kanban cards should now be clickable.")
        print("\nExpected behavior:")
        print("- Clicking on an Issue ticket opens the Issue form view")
        print("- Clicking on an Access ticket opens the Access form view")
        print("- Clicking on a Purchase ticket opens the Purchase form view")
        print("- SLA breached tickets will have a red background")
    else:
        print("✗ Some checks failed. Please review the implementation.")
    
    return 0 if all_passed else 1

if __name__ == '__main__':
    sys.exit(main())