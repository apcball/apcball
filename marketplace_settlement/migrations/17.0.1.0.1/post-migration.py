"""
Migration script to update existing vendor bills with direct settlement links
This script will convert existing Many2many relationships to direct links
"""

from odoo import api, SUPERUSER_ID
import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migrate existing vendor bill relationships to use direct settlement links
    """
    if not version:
        return

    env = api.Environment(cr, SUPERUSER_ID, {})
    
    _logger.info("Starting migration to convert vendor bill relationships to direct links")
    
    try:
        # Find all settlements with vendor bills linked via the old Many2many relation
        settlements = env['marketplace.settlement'].search([
            ('old_vendor_bill_ids', '!=', False)
        ])
        
        for settlement in settlements:
            _logger.info(f"Processing settlement {settlement.name}")
            
            # Get vendor bills from the old Many2many field
            vendor_bills = settlement.old_vendor_bill_ids
            
            for bill in vendor_bills:
                # Only update if not already linked
                if not bill.x_settlement_id:
                    bill.x_settlement_id = settlement.id
                    _logger.info(f"Linked bill {bill.name} to settlement {settlement.name}")
                else:
                    _logger.warning(f"Bill {bill.name} already linked to settlement {bill.x_settlement_id.name}")
        
        _logger.info("Migration completed successfully")
        
    except Exception as e:
        _logger.error(f"Migration failed: {str(e)}")
        raise
