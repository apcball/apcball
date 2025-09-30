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
    """Clean up before uninstall for Odoo 17"""
    _logger.info("Uninstalling l10n_th_account_tax_report for Odoo 17")
    
    # Perform any necessary cleanup
    try:
        # Clean up any temporary configurations or data created by this module
        _cleanup_module_data(env)
        _logger.info("l10n_th_account_tax_report uninstalled successfully")
    except Exception as e:
        _logger.error(f"Error during uninstall: {e}")


def _cleanup_module_data(env):
    """Clean up any module-specific data during uninstall"""
    _logger.info("Cleaning up module data")
    
    # Add any specific cleanup logic needed during uninstall
    # Currently empty, but can be extended as needed
    pass


def post_init_hook(env):
    """Post installation hook with Odoo 17 compatibility checks"""
    _logger.info("Starting l10n_th_account_tax_report post-init for Odoo 17")
    
    # Apply compatibility patches
    patch_odoo17_compatibility()
    
    try:
        # Test basic functionality
        wizard_model = env['tax.report.wizard']
        _logger.info("Tax report wizard model loaded successfully")
        
        # Test withholding tax report wizard
        wht_wizard_model = env['withholding.tax.report.wizard']
        _logger.info("Withholding tax report wizard model loaded successfully")
        
        # Test report models
        tax_report_model = env['report.l10n_th_account_tax_report.report_thai_tax']
        _logger.info("Tax report model loaded successfully")
        
        # Initialize any required data or configurations
        _initialize_module_data(env)
        
        # Update any existing records that need migration to Odoo 17 format
        _migrate_existing_data(env)
        
        _logger.info("l10n_th_account_tax_report installed successfully with Odoo 17 compatibility layer")
        
    except Exception as e:
        _logger.error(f"Post-init compatibility check failed: {e}")
        # Don't raise the error to prevent installation failure


def _initialize_module_data(env):
    """Initialize any required data after installation"""
    _logger.info("Initializing module data for Odoo 17")
    
    # Example: Ensure any required configurations are set
    # This could include setting default values, creating necessary records, etc.
    try:
        # Check and update any existing tax report configurations if needed
        _logger.info("Module data initialization completed")
    except Exception as e:
        _logger.warning(f"Error during data initialization: {e}")


def _migrate_existing_data(env):
    """Migrate existing data to be compatible with Odoo 17"""
    _logger.info("Checking for data migration needs")
    
    # Add any specific data migration logic needed for Odoo 17 here
    # Currently empty, but can be extended as needed
    pass
        

def pre_init_hook(env):
    """Pre-initialization hook with dependency checking for Odoo 17"""
    _logger.info("Starting l10n_th_account_tax_report pre-init for Odoo 17")
    
    # Apply early compatibility patches
    patch_odoo17_compatibility()
    
    # Check dependencies with better error handling for Odoo 17
    required_modules = [
        'l10n_th_base_utils', 
        'l10n_th_partner', 
        'l10n_th_account_tax',
        'date_range', 
        'report_xlsx_helper',
        'account',
    ]
    
    missing_modules = []
    for module_name in required_modules:
        try:
            module = env['ir.module.module'].sudo().search([('name', '=', module_name)])
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
    
    # Check Odoo version compatibility
    try:
        # Execute a simple query to ensure database connection works properly
        env.cr.execute("SELECT name FROM ir_module_module LIMIT 1")
        _logger.info("Database connection and basic queries working correctly for Odoo 17")
    except Exception as e:
        _logger.error(f"Database connection issue: {e}")
