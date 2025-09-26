from odoo import SUPERUSER_ID
from odoo.api import Environment

def post_init_hook(cr, registry):
    env = Environment(cr, SUPERUSER_ID, {})
    utils = env['hr.expense.advance.journal.utils']
    # Get the configured clearing journal and ensure it has a sequence
    clearing_journal_id = env['ir.config_parameter'].sudo().get_param('employee_advance.advance_default_clearing_journal_id')
    if clearing_journal_id:
        journal = env['account.journal'].browse(int(clearing_journal_id))
        if journal.exists():
            utils.ensure_journal_sequence(journal)