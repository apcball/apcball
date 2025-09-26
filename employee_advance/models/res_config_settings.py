from odoo import models, fields


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    advance_notify_user_id = fields.Many2one(
        'res.users',
        string='Notify User for Advance Bills',
        config_parameter='employee_advance.advance_notify_user_id'
    )
    advance_notify_group_id = fields.Many2one(
        'res.groups',
        string='Notify Group for Advance Bills',
        config_parameter='employee_advance.advance_notify_group_id'
    )
    advance_notify_activity_type_id = fields.Many2one(
        'mail.activity.type',
        string='Activity Type for Advance Bills',
        config_parameter='employee_advance.advance_notify_activity_type_id'
    )
    advance_notify_deadline_days = fields.Integer(
        string='Activity Deadline Days',
        default=1,
        config_parameter='employee_advance.advance_notify_deadline_days'
    )
    advance_default_clearing_journal_id = fields.Many2one(
        'account.journal',
        string='Default Clearing Journal',
        domain=[('type', '=', 'general')],
        config_parameter='employee_advance.advance_default_clearing_journal_id'
    )