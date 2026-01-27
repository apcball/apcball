from odoo import SUPERUSER_ID
from odoo.api import Environment
import logging

_logger = logging.getLogger(__name__)

def pre_init_hook(env):
    """Clean up wizard tables before module upgrade to prevent constraint errors"""
    cr = env.cr
    try:
        # Clean up advance_refill_base_wizard table if it exists
        cr.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'advance_refill_base_wizard')")
        if cr.fetchone()[0]:
            cr.execute("DELETE FROM advance_refill_base_wizard")
            _logger.info("🧹 Cleaned up advance_refill_base_wizard table")
        
        # Clean up advance_settlement_wizard table if it exists  
        cr.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'advance_settlement_wizard')")
        if cr.fetchone()[0]:
            cr.execute("DELETE FROM advance_settlement_wizard")
            _logger.info("🧹 Cleaned up advance_settlement_wizard table")
            
        cr.commit()
        _logger.info("✅ Wizard cleanup completed successfully")
    except Exception as e:
        _logger.warning("⚠️ Wizard cleanup failed: %s", str(e))
        cr.rollback()

def post_init_hook(env):
    # Using the environment directly as provided by Odoo framework
    utils = env['hr.expense.advance.journal.utils']
    # Get the configured clearing journal and ensure it has a sequence
    clearing_journal_id = env['ir.config_parameter'].sudo().get_param('employee_advance.advance_default_clearing_journal_id')
    if clearing_journal_id:
        journal = env['account.journal'].browse(int(clearing_journal_id))
        if journal.exists():
            utils.ensure_journal_sequence(journal)
    
    # Add new columns to the database table if they don't exist
    cr = env.cr
    
    # Add clear_mode column
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'hr_expense_sheet' AND column_name = 'clear_mode'
    """)
    if not cr.fetchone():
        _logger.info("Adding clear_mode column to hr_expense_sheet table")
        cr.execute("""
            ALTER TABLE hr_expense_sheet 
            ADD COLUMN clear_mode varchar
        """)
    
    # Add is_billed column
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'hr_expense_sheet' AND column_name = 'is_billed'
    """)
    if not cr.fetchone():
        _logger.info("Adding is_billed column to hr_expense_sheet table")
        cr.execute("""
            ALTER TABLE hr_expense_sheet 
            ADD COLUMN is_billed boolean DEFAULT false
        """)
        
    # Add vendor_id column to hr_expense table
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'hr_expense' AND column_name = 'vendor_id'
    """)
    if not cr.fetchone():
        _logger.info("Adding vendor_id column to hr_expense table")
        cr.execute("""
            ALTER TABLE hr_expense 
            ADD COLUMN vendor_id integer
        """)
    
    # Add advance_box_id column to hr_employee table
    cr.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'hr_employee' AND column_name = 'advance_box_id'
    """)
    if not cr.fetchone():
        _logger.info("Adding advance_box_id column to hr_employee table")
        cr.execute("""
            ALTER TABLE hr_employee 
            ADD COLUMN advance_box_id integer
        """)
    
    # Check if the many2many relationship table exists for bill_ids
    # The table name format for many2many is typically: model1_model2_rel
    cr.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_name = 'hr_expense_sheet_account_move_rel'
    """)
    if not cr.fetchone():
        _logger.info("Creating hr_expense_sheet_account_move_rel table")
        cr.execute("""
            CREATE TABLE hr_expense_sheet_account_move_rel (
                expense_sheet_id INTEGER,
                move_id INTEGER
            )
        """)
    
    cr.commit()  # Commit the changes to the database