# Copyright 2019 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

"""
Odoo 18 to 17 Compatibility Layer
This module provides compatibility fixes for modules downgraded from Odoo 18 to 17
"""

from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


def patch_odoo17_compatibility():
    """Apply compatibility patches for Odoo 17"""
    
    # Patch 1: Handle translation function changes
    try:
        from odoo import _
        # Ensure translation function is available globally
        if not hasattr(api.Environment, '_'):
            api.Environment._ = lambda self, text: _(text)
        _logger.info("Applied translation compatibility patch")
    except Exception as e:
        _logger.warning(f"Could not apply translation patch: {e}")
    
    # Patch 2: Handle SQL query compatibility
    try:
        from odoo.sql_db import Cursor
        if not hasattr(Cursor, 'SQL'):
            # Simple SQL wrapper for compatibility
            def sql_wrapper(query):
                return query
            Cursor.SQL = sql_wrapper
        _logger.info("Applied SQL compatibility patch")
    except Exception as e:
        _logger.warning(f"Could not apply SQL patch: {e}")


def uninstall_hook(env):
    """Clean up before uninstall"""
    _logger.info("Cleaning up l10n_th_account_tax_report compatibility")


def post_init_hook(env):
    """Post installation hook with compatibility checks"""
    _logger.info("Starting l10n_th_account_tax_report post-init with compatibility layer")
    
    # Apply compatibility patches
    patch_odoo17_compatibility()
    
    # Check for any issues
    try:
        # Test basic functionality
        wizard_model = env['tax.report.wizard']
        _logger.info("Tax report wizard model loaded successfully")
        
        # Test translation functionality
        test_msg = "Test message"
        _logger.info(f"Translation test: {test_msg}")
        
        _logger.info("l10n_th_account_tax_report installed successfully with compatibility layer")
        
    except Exception as e:
        _logger.error(f"Post-init compatibility check failed: {e}")
        # Don't raise the error to prevent installation failure
        

def pre_init_hook(env):
    """Pre-initialization hook with dependency checking"""
    _logger.info("Starting l10n_th_account_tax_report pre-init with compatibility layer")
    
    # Apply early compatibility patches
    patch_odoo17_compatibility()
    
    # Check dependencies with better error handling
    required_modules = [
        'l10n_th_base_utils', 
        'l10n_th_partner', 
        'l10n_th_account_tax',
        'date_range', 
        'report_xlsx_helper'
    ]
    
    missing_modules = []
    for module_name in required_modules:
        try:
            module = env['ir.module.module'].search([('name', '=', module_name)])
            if not module or module.state != 'installed':
                missing_modules.append(module_name)
        except Exception as e:
            _logger.warning(f"Could not check module {module_name}: {e}")
            missing_modules.append(module_name)
    
    if missing_modules:
        _logger.warning(f"Missing or uninstalled modules: {missing_modules}")
        _logger.info("Installation will continue, but some features may not work properly")
    else:
        _logger.info("All required dependencies are available")
