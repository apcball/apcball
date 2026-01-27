from odoo import fields, models

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    expense_acc_manager_id = fields.Many2one(
        'res.users',
        string='ACC Manager',
        config_parameter='buz_approval_expenses.expense_acc_manager_id',
        domain=[('share', '=', False)]
    )