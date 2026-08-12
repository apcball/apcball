from odoo import fields, models


class ResCompany(models.Model):
    _inherit = 'res.company'

    helpdesk_line_group_id = fields.Many2one(
        'buz.helpdesk.line.group', string='Helpdesk LINE Group', ondelete='set null',
        help='LINE group that receives new Helpdesk Ticket notifications for this company.',
    )
    helpdesk_line_enabled = fields.Boolean(string='Enable Helpdesk LINE Notifications', default=False)

