import logging
from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)

def migrate(cr, version):
    _logger.info('Migration to version %s: Starting post-migration script', version)
    
    # Create an environment with the cursor
    env = api.Environment(cr, SUPERUSER_ID, {})
    
    # Import the post_init_hook from the hooks file
    from odoo.addons.employee_advance.hooks import post_init_hook
    
    # Run the post_init_hook logic
    try:
        post_init_hook(env)
        _logger.info('Migration to version %s: post_init_hook executed successfully', version)
    except Exception as e:
        _logger.error('Migration to version %s: Failed to execute post_init_hook: %s', version, str(e))
