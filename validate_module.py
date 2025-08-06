#!/usr/bin/env python3
"""
Test script to validate hr_expense_advance_clearing module for Odoo 17
"""

import sys
import os

def check_module_structure():
    """Check if all required files exist"""
    base_path = "/opt/instance1/odoo17/custom-addons/hr_expense_advance_clearing"
    
    required_files = [
        "__manifest__.py",
        "__init__.py",
        "models/__init__.py",
        "models/hr_expense.py",
        "models/hr_expense_sheet.py",
        "models/hr_employee_base.py",
        "models/account_move.py",
        "models/account_payment.py",
        "wizard/__init__.py",
        "wizard/account_payment_register.py",
        "data/advance_product.xml",
        "views/hr_expense_views.xml",
        "views/hr_employee_views.xml",
        "views/hr_employee_public_views.xml",
        "views/account_payment_view.xml",
    ]
    
    missing_files = []
    for file_path in required_files:
        full_path = os.path.join(base_path, file_path)
        if not os.path.exists(full_path):
            missing_files.append(file_path)
    
    if missing_files:
        print("❌ Missing required files:")
        for file_path in missing_files:
            print(f"  - {file_path}")
        return False
    else:
        print("✅ All required files are present")
        return True

def check_manifest():
    """Check manifest file for Odoo 17 compatibility"""
    manifest_path = "/opt/instance1/odoo17/custom-addons/hr_expense_advance_clearing/__manifest__.py"
    
    try:
        with open(manifest_path, 'r') as f:
            content = f.read()
            
        # Check version starts with 17.0
        if '"version": "17.0' in content:
            print("✅ Version is correctly set for Odoo 17")
        else:
            print("❌ Version should start with 17.0")
            return False
            
        # Check dependencies
        if '"hr_expense"' in content:
            print("✅ Required hr_expense dependency is present")
        else:
            print("❌ hr_expense dependency is missing")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Error reading manifest: {e}")
        return False

def check_python_syntax():
    """Check Python files for syntax errors"""
    import py_compile
    import tempfile
    
    base_path = "/opt/instance1/odoo17/custom-addons/hr_expense_advance_clearing"
    python_files = []
    
    # Find all Python files
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.endswith('.py'):
                python_files.append(os.path.join(root, file))
    
    syntax_errors = []
    for py_file in python_files:
        try:
            py_compile.compile(py_file, doraise=True)
        except py_compile.PyCompileError as e:
            syntax_errors.append((py_file, str(e)))
    
    if syntax_errors:
        print("❌ Python syntax errors found:")
        for file_path, error in syntax_errors:
            print(f"  - {file_path}: {error}")
        return False
    else:
        print("✅ All Python files have correct syntax")
        return True

def main():
    """Run all validation checks"""
    print("🔍 Validating hr_expense_advance_clearing module for Odoo 17...")
    print("=" * 60)
    
    checks = [
        ("Module Structure", check_module_structure),
        ("Manifest File", check_manifest),
        ("Python Syntax", check_python_syntax),
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        print(f"\n📋 {check_name}:")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 60)
    if all_passed:
        print("🎉 All validation checks passed! Module should be compatible with Odoo 17.")
        print("\n📝 Next steps:")
        print("1. Install the module in Odoo 17")
        print("2. Run the automated tests")
        print("3. Test the advance and clearing functionality")
    else:
        print("⚠️  Some validation checks failed. Please fix the issues before installing.")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
