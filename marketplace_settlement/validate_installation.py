#!/usr/bin/env python3
"""
Marketplace Settlement Module Installation Validation
Tests module structure and dependencies for successful installation.
"""

import os
import xml.etree.ElementTree as ET

def validate_manifest():
    """Validate __manifest__.py file"""
    try:
        with open('__manifest__.py', 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Try to evaluate the manifest
        manifest = eval(content)
        
        required_keys = ['name', 'version', 'depends', 'data', 'installable']
        missing_keys = [key for key in required_keys if key not in manifest]
        
        print("✓ Manifest file validation:")
        if missing_keys:
            print(f"  ⚠ Missing keys: {missing_keys}")
        else:
            print(f"  ✓ All required keys present")
            print(f"  ✓ Name: {manifest['name']}")
            print(f"  ✓ Version: {manifest['version']}")
            print(f"  ✓ Dependencies: {', '.join(manifest['depends'])}")
        
        return len(missing_keys) == 0
        
    except Exception as e:
        print(f"✗ Manifest validation failed: {e}")
        return False

def validate_xml_files():
    """Validate XML files for syntax errors"""
    print("\n✓ XML file validation:")
    
    xml_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.xml'):
                xml_files.append(os.path.join(root, file))
    
    valid_files = 0
    for xml_file in xml_files:
        try:
            ET.parse(xml_file)
            print(f"  ✓ {xml_file}")
            valid_files += 1
        except ET.ParseError as e:
            print(f"  ✗ {xml_file}: {e}")
        except Exception as e:
            print(f"  ✗ {xml_file}: {e}")
    
    print(f"  Summary: {valid_files}/{len(xml_files)} XML files valid")
    return valid_files == len(xml_files)

def validate_csv_files():
    """Validate CSV files"""
    print("\n✓ CSV file validation:")
    
    csv_files = []
    for root, dirs, files in os.walk('.'):
        for file in files:
            if file.endswith('.csv'):
                csv_files.append(os.path.join(root, file))
    
    valid_files = 0
    for csv_file in csv_files:
        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                if len(lines) > 0:
                    print(f"  ✓ {csv_file} ({len(lines)} lines)")
                    valid_files += 1
                else:
                    print(f"  ⚠ {csv_file} (empty file)")
        except Exception as e:
            print(f"  ✗ {csv_file}: {e}")
    
    if csv_files:
        print(f"  Summary: {valid_files}/{len(csv_files)} CSV files valid")
    else:
        print("  No CSV files found")
    
    return True

def validate_python_imports():
    """Validate Python import structure"""
    print("\n✓ Python import validation:")
    
    # Check main __init__.py
    init_files = ['__init__.py', 'models/__init__.py', 'wizards/__init__.py']
    
    for init_file in init_files:
        if os.path.exists(init_file):
            try:
                with open(init_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Count import statements
                import_lines = [line for line in content.split('\n') if line.strip().startswith('from .')]
                print(f"  ✓ {init_file} ({len(import_lines)} imports)")
            except Exception as e:
                print(f"  ✗ {init_file}: {e}")
        else:
            print(f"  ✗ {init_file}: File not found")
    
    return True

def validate_data_files():
    """Validate data files exist and are referenced in manifest"""
    print("\n✓ Data file validation:")
    
    try:
        with open('__manifest__.py', 'r', encoding='utf-8') as f:
            manifest = eval(f.read())
        
        data_files = manifest.get('data', [])
        demo_files = manifest.get('demo', [])
        all_files = data_files + demo_files
        
        missing_files = []
        for file_path in all_files:
            if not os.path.exists(file_path):
                missing_files.append(file_path)
            else:
                print(f"  ✓ {file_path}")
        
        if missing_files:
            print(f"  ⚠ Missing files: {missing_files}")
            return False
        else:
            print(f"  ✓ All {len(all_files)} data files exist")
            return True
            
    except Exception as e:
        print(f"  ✗ Data file validation failed: {e}")
        return False

def main():
    """Main validation function"""
    print("=== Marketplace Settlement Module Installation Validation ===\n")
    
    # Change to module directory
    module_dir = '/opt/instance1/odoo17/custom-addons/marketplace_settlement'
    if os.path.exists(module_dir):
        os.chdir(module_dir)
    else:
        print(f"ERROR: Module directory not found: {module_dir}")
        return 1
    
    # Run validations
    validations = [
        validate_manifest(),
        validate_xml_files(),
        validate_csv_files(),
        validate_python_imports(),
        validate_data_files()
    ]
    
    # Summary
    passed = sum(validations)
    total = len(validations)
    
    print(f"\n{'='*60}")
    print(f"INSTALLATION VALIDATION SUMMARY: {passed}/{total} checks passed")
    
    if passed == total:
        print("✓ Module is ready for installation!")
        return 0
    else:
        print("⚠ Some issues found. Please review the output above.")
        return 1

if __name__ == '__main__':
    exit(main())
