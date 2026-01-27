#!/usr/bin/env python3
"""
Comprehensive debug script to identify all potential sources of the TypeError
"""

import os
import re

def find_all_compute_fields():
    """Find all compute fields with search=True in the module"""
    
    print("=== Comprehensive Field Analysis ===")
    
    module_path = '/opt/instance1/odoo17/custom-addons/buz_warranty_management'
    
    for root, dirs, files in os.walk(module_path):
        for file in files:
            if file.endswith('.py') and not file.startswith('debug_') and not file.startswith('verify_'):
                file_path = os.path.join(root, file)
                print(f"\n--- Analyzing {file_path} ---")
                
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Find all field definitions
                    field_pattern = r'(\w+)\s*=\s*fields\.\w+\([^)]*search\s*=\s*True[^)]*\)'
                    matches = re.findall(field_pattern, content, re.DOTALL)
                    
                    if matches:
                        print(f"Fields with search=True: {matches}")
                        
                        # For each field, check if corresponding search method exists
                        for field_name in matches:
                            search_method_name = f'_search_{field_name}'
                            search_method_pattern = f'def {search_method_name}\('
                            
                            if re.search(search_method_pattern, content):
                                # Check if it has @api.model decorator
                                method_start = content.find(search_method_pattern)
                                context_start = max(0, method_start - 200)
                                context = content[context_start:method_start + 100]
                                
                                if '@api.model' in context:
                                    print(f"  ✓ {field_name}: Has proper @api.model search method")
                                else:
                                    print(f"  ✗ {field_name}: Search method missing @api.model decorator")
                            else:
                                print(f"  ✗ {field_name}: Missing search method {search_method_name}")
                    else:
                        print("No fields with search=True found")
                        
                except Exception as e:
                    print(f"Error analyzing {file_path}: {e}")

def check_for_other_issues():
    """Check for other potential issues that could cause the error"""
    
    print("\n=== Checking for Other Potential Issues ===")
    
    # Check for any field with unusual parameters
    module_path = '/opt/instance1/odoo17/custom-addons/buz_warranty_management'
    
    for root, dirs, files in os.walk(module_path):
        for file in files:
            if file.endswith('.py') and not file.startswith('debug_') and not file.startswith('verify_'):
                file_path = os.path.join(root, file)
                
                try:
                    with open(file_path, 'r') as f:
                        content = f.read()
                    
                    # Look for any field definitions with potential issues
                    field_lines = []
                    lines = content.split('\n')
                    
                    for i, line in enumerate(lines):
                        if 'fields.' in line and '(' in line:
                            # Get the full field definition (might span multiple lines)
                            field_def = line
                            j = i + 1
                            paren_count = line.count('(') - line.count(')')
                            
                            while j < len(lines) and paren_count > 0:
                                field_def += '\n' + lines[j]
                                paren_count += lines[j].count('(') - lines[j].count(')')
                                j += 1
                            
                            field_lines.append((i+1, field_def))
                    
                    # Check each field definition for potential issues
                    for line_num, field_def in field_lines:
                        if 'determine' in field_def:
                            print(f"Line {line_num}: Field with 'determine' parameter found:")
                            print(field_def)
                            print("  ⚠️  This could be the source of the error!")
                        
                        if 'search=' in field_def and 'True' in field_def:
                            # Extract field name
                            field_match = re.match(r'(\w+)\s*=', field_def.strip())
                            if field_match:
                                field_name = field_match.group(1)
                                print(f"Line {line_num}: Field '{field_name}' has search=True")
                                
                except Exception as e:
                    print(f"Error checking {file_path}: {e}")

if __name__ == "__main__":
    find_all_compute_fields()
    check_for_other_issues()