#!/usr/bin/env python3
"""
Marketplace Settlement Module Workflow Validation Script
This script validates the workflow connections between different processes.
"""

import os
import sys
import ast

def check_model_methods(file_path, expected_methods):
    """Check if a model file contains expected methods"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        tree = ast.parse(content)
        
        found_methods = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith('action_'):
                found_methods.append(node.name)
        
        missing_methods = set(expected_methods) - set(found_methods)
        
        return {
            'file': file_path,
            'found_methods': found_methods,
            'missing_methods': list(missing_methods),
            'status': 'OK' if not missing_methods else 'MISSING_METHODS'
        }
    except Exception as e:
        return {
            'file': file_path,
            'error': str(e),
            'status': 'ERROR'
        }

def validate_workflow():
    """Validate the main workflow connections"""
    
    # Expected methods for each model
    expected_methods = {
        'models/settlement.py': [
            'action_create_settlement',
            'action_preview_settlement', 
            'action_view_invoices',
            'action_view_settlement_move',
            'action_netoff_ar_ap',
            'action_open_netting_wizard',
            'action_view_netting_move',
            'action_reverse_netting',
            'action_generate_fee_allocations',
            'action_view_fee_allocations',
            'action_import_fee_allocations_csv'
        ],
        'wizards/marketplace_settlement_wizard.py': [
            'action_create',
            'action_refresh_invoices'
        ],
        'wizards/marketplace_netting_wizard.py': [
            'action_confirm_netting',
            'action_auto_select_bills',
            'action_clear_selection'
        ],
        'wizards/settlement_preview_wizard.py': [
            'action_create_settlement',
            'action_cancel'
        ]
    }
    
    results = []
    
    for file_path, methods in expected_methods.items():
        if os.path.exists(file_path):
            result = check_model_methods(file_path, methods)
            results.append(result)
        else:
            results.append({
                'file': file_path,
                'status': 'FILE_NOT_FOUND'
            })
    
    return results

def check_view_connections():
    """Check if view files have proper action connections"""
    view_files = [
        'views/marketplace_settlement_wizard_views.xml',
        'views/marketplace_netting_wizard_views.xml', 
        'views/settlement_preview_wizard_views.xml'
    ]
    
    required_actions = [
        'action_create_settlement',
        'action_open_netting_wizard',
        'action_netoff_ar_ap',
        'action_preview_settlement'
    ]
    
    view_results = []
    
    for view_file in view_files:
        if os.path.exists(view_file):
            try:
                with open(view_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                found_actions = []
                for action in required_actions:
                    if action in content:
                        found_actions.append(action)
                
                view_results.append({
                    'file': view_file,
                    'found_actions': found_actions,
                    'status': 'OK'
                })
            except Exception as e:
                view_results.append({
                    'file': view_file,
                    'error': str(e),
                    'status': 'ERROR'
                })
        else:
            view_results.append({
                'file': view_file,
                'status': 'FILE_NOT_FOUND'
            })
    
    return view_results

def main():
    """Main validation function"""
    print("=== Marketplace Settlement Module Workflow Validation ===\n")
    
    # Change to module directory
    module_dir = '/opt/instance1/odoo17/custom-addons/marketplace_settlement'
    if os.path.exists(module_dir):
        os.chdir(module_dir)
    else:
        print(f"ERROR: Module directory not found: {module_dir}")
        sys.exit(1)
    
    # Validate model methods
    print("1. Validating Model Action Methods:")
    print("-" * 40)
    
    model_results = validate_workflow()
    for result in model_results:
        print(f"File: {result['file']}")
        print(f"Status: {result['status']}")
        
        if result['status'] == 'OK':
            print(f"  ✓ Found {len(result['found_methods'])} action methods")
        elif result['status'] == 'MISSING_METHODS':
            print(f"  ⚠ Missing methods: {', '.join(result['missing_methods'])}")
        elif result['status'] == 'ERROR':
            print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        elif result['status'] == 'FILE_NOT_FOUND':
            print(f"  ✗ File not found")
        
        print()
    
    # Validate view connections
    print("2. Validating View Action Connections:")
    print("-" * 40)
    
    view_results = check_view_connections()
    for result in view_results:
        print(f"File: {result['file']}")
        print(f"Status: {result['status']}")
        
        if result['status'] == 'OK':
            print(f"  ✓ Found actions: {', '.join(result['found_actions'])}")
        elif result['status'] == 'ERROR':
            print(f"  ✗ Error: {result.get('error', 'Unknown error')}")
        elif result['status'] == 'FILE_NOT_FOUND':
            print(f"  ✗ File not found")
        
        print()
    
    # Summary
    total_files = len(model_results) + len(view_results)
    ok_files = len([r for r in model_results + view_results if r['status'] == 'OK'])
    
    print("=" * 50)
    print(f"SUMMARY: {ok_files}/{total_files} files validated successfully")
    
    if ok_files == total_files:
        print("✓ All workflow connections are properly implemented!")
        return 0
    else:
        print("⚠ Some issues found. Please review the output above.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
