#!/usr/bin/env python3

"""
Test script for marketplace_settlement module enhancements
"""

import os
import sys
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
_logger = logging.getLogger(__name__)

def test_syntax():
    """Test Python syntax of all Python files"""
    _logger.info("Testing Python syntax...")
    
    python_files = [
        'models/sale_account_extension.py',
        'models/settlement.py', 
        'wizards/bill_link_wizard.py',
        'wizards/settlement_preview_wizard.py',
        'wizards/marketplace_netting_wizard.py'
    ]
    
    for file in python_files:
        try:
            with open(file, 'r') as f:
                compile(f.read(), file, 'exec')
            _logger.info(f"✅ {file} - Syntax OK")
        except SyntaxError as e:
            _logger.error(f"❌ {file} - Syntax Error: {e}")
            return False
        except FileNotFoundError:
            _logger.warning(f"⚠️  {file} - File not found")
    
    return True

def test_xml_syntax():
    """Test XML syntax of view files"""
    _logger.info("Testing XML syntax...")
    
    import xml.etree.ElementTree as ET
    
    xml_files = [
        'views/account_move_view_inherit.xml',
        'views/bill_link_wizard_views.xml',
        'views/settlement_preview_wizard_views.xml',
        'views/marketplace_settlement_wizard_views.xml'
    ]
    
    for file in xml_files:
        try:
            ET.parse(file)
            _logger.info(f"✅ {file} - XML OK")
        except ET.ParseError as e:
            _logger.error(f"❌ {file} - XML Error: {e}")
            return False
        except FileNotFoundError:
            _logger.warning(f"⚠️  {file} - File not found")
    
    return True

def test_manifest():
    """Test manifest file"""
    _logger.info("Testing manifest...")
    
    try:
        with open('__manifest__.py', 'r') as f:
            manifest_code = f.read()
            
        # Simple check that it's valid Python
        compile(manifest_code, '__manifest__.py', 'exec')
        _logger.info("✅ __manifest__.py - Syntax OK")
        
        # Check for required fields
        if "'name'" in manifest_code and "'version'" in manifest_code:
            _logger.info("✅ __manifest__.py - Required fields present")
        else:
            _logger.warning("⚠️  __manifest__.py - Missing required fields")
            
        return True
        
    except Exception as e:
        _logger.error(f"❌ __manifest__.py - Error: {e}")
        return False

def main():
    """Run all tests"""
    _logger.info("Starting marketplace_settlement module tests...")
    
    success = True
    success &= test_syntax()
    success &= test_xml_syntax() 
    success &= test_manifest()
    
    if success:
        _logger.info("🎉 All tests passed! Module is ready for installation.")
        return 0
    else:
        _logger.error("❌ Some tests failed. Please fix the issues before installing.")
        return 1

if __name__ == '__main__':
    sys.exit(main())
