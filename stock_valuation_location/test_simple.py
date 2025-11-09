#!/usr/bin/env python3
"""
Simple test to verify stock_valuation_location module structure
"""

import os
import sys
import ast

MODULE_PATH = os.path.dirname(os.path.abspath(__file__))

def test_python_syntax():
    """Test that all Python files have valid syntax"""
    python_files = [
        '__init__.py',
        '__manifest__.py',
        'models/__init__.py',
        'models/stock_valuation_layer.py',
    ]
    
    for file_path in python_files:
        full_path = os.path.join(MODULE_PATH, file_path)
        if not os.path.exists(full_path):
            print(f"❌ Missing file: {file_path}")
            return False
        
        try:
            with open(full_path, 'r') as f:
                ast.parse(f.read())
            print(f"✓ {file_path} - syntax OK")
        except SyntaxError as e:
            print(f"❌ {file_path} - syntax error: {e}")
            return False
    
    return True

def test_manifest():
    """Test manifest structure"""
    manifest_path = os.path.join(MODULE_PATH, '__manifest__.py')
    
    with open(manifest_path, 'r') as f:
        manifest = eval(f.read())
    
    required_keys = ['name', 'version', 'depends', 'data']
    for key in required_keys:
        if key not in manifest:
            print(f"❌ Missing required key in manifest: {key}")
            return False
    
    # Check version bump
    if manifest['version'] != '17.0.1.0.2':
        print(f"❌ Expected version 17.0.1.0.2, got {manifest['version']}")
        return False
    
    # Check no SQL wizard references
    if any('fast_sql' in item.lower() for item in manifest.get('data', [])):
        print(f"❌ SQL wizard references still in manifest")
        return False
    
    print(f"✓ Manifest structure OK")
    print(f"  - Name: {manifest['name']}")
    print(f"  - Version: {manifest['version']}")
    print(f"  - Data files: {len(manifest['data'])}")
    
    return True

def test_no_sql_functions():
    """Test that SQL functions are removed"""
    model_path = os.path.join(MODULE_PATH, 'models/stock_valuation_layer.py')
    
    with open(model_path, 'r') as f:
        content = f.read()
    
    forbidden_terms = [
        '_sql_fast_fill_location',
        'action_recompute_stock_valuation_location',
        'pg_try_advisory',
        'statement_timeout'
    ]
    
    for term in forbidden_terms:
        if term in content:
            print(f"❌ Found forbidden SQL term: {term}")
            return False
    
    print(f"✓ No SQL functions found")
    return True

def test_required_function():
    """Test that compute function exists"""
    model_path = os.path.join(MODULE_PATH, 'models/stock_valuation_layer.py')
    
    with open(model_path, 'r') as f:
        content = f.read()
    
    if '_compute_location_id' not in content:
        print(f"❌ Missing _compute_location_id function")
        return False
    
    if 'location_id = fields.Many2one' not in content:
        print(f"❌ Missing location_id field definition")
        return False
    
    print(f"✓ Required compute function exists")
    return True

def main():
    print("=" * 60)
    print("Testing stock_valuation_location module")
    print("=" * 60)
    print()
    
    tests = [
        ('Python syntax', test_python_syntax),
        ('Manifest structure', test_manifest),
        ('No SQL functions', test_no_sql_functions),
        ('Required functions', test_required_function),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        print("-" * 40)
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test error: {e}")
            failed += 1
    
    print()
    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    return 0 if failed == 0 else 1

if __name__ == '__main__':
    sys.exit(main())
