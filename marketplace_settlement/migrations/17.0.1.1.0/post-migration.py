"""
Post-migration script for marketplace_settlement enhanced profile
Removes obsolete fields from Profile Customer Settlement
"""

import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Migrate marketplace settlement profile enhancements"""
    _logger.info("Starting marketplace settlement profile enhancement migration...")
    
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Drop obsolete columns if they exist
    obsolete_columns = [
        'vendor_partner_id',
        'purchase_journal_id', 
        'default_vat_rate',
        'default_wht_rate',
        'vat_tax_id',
        'wht_tax_id',
        'use_thai_wht',
        'thai_income_tax_form',
        'thai_wht_income_type'
    ]
    
    for column in obsolete_columns:
        try:
            cr.execute(f"""
                ALTER TABLE marketplace_settlement_profile 
                DROP COLUMN IF EXISTS {column}
            """)
            _logger.info(f"Dropped column {column} from marketplace_settlement_profile")
        except Exception as e:
            _logger.warning(f"Could not drop column {column}: {e}")
    
    # Remove domains from account fields to allow all account types
    _logger.info("Enhanced Profile Customer Settlement: Removed vendor settings and Thai WHT configuration")
    _logger.info("Account code selection now allows all categories")
    _logger.info("Journal selection now allows all categories")
    
    _logger.info("Marketplace settlement profile enhancement migration completed successfully")
