from . import models

def _post_init_hook(cr, registry):
    """Post-install script"""
    env = registry['base'].env()
    # Grant submit rights to all users
    users = env['res.users'].search([])
    expense_user_group = env.ref('hr_expense.group_hr_expense_user')
    for user in users:
        expense_user_group.write({'users': [(4, user.id)]})