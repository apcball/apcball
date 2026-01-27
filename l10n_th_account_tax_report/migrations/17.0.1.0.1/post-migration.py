# Copyright 2026 Ecosoft Co., Ltd (https://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """
    Migration script to update legacy tax invoice records:
    1. Set company_id for records without it
    2. Set tax_amount = balance for legacy records that don't have tax_amount
    """
    if not version:
        return
    
    _logger.info("Starting migration for l10n_th_account_tax_report to version 17.0.1.0.1")
    
    # Update company_id for records without move_line_id and without company_id
    cr.execute("""
        UPDATE account_move_tax_invoice
        SET company_id = (SELECT id FROM res_company ORDER BY id LIMIT 1)
        WHERE move_line_id IS NULL 
        AND company_id IS NULL
        AND (SELECT COUNT(*) FROM res_company) > 0
    """)
    updated_company = cr.rowcount
    _logger.info(f"Updated company_id for {updated_company} legacy tax invoice records")
    
    # Update tax_amount for records without move_line_id and without tax_amount
    # Copy from balance field if available, otherwise set to 0
    cr.execute("""
        UPDATE account_move_tax_invoice
        SET tax_amount = COALESCE(balance, 0.0)
        WHERE move_line_id IS NULL 
        AND tax_amount IS NULL
    """)
    updated_tax_amount = cr.rowcount
    _logger.info(f"Updated tax_amount for {updated_tax_amount} legacy tax invoice records")
    
    _logger.info("Completed migration for l10n_th_account_tax_report")
