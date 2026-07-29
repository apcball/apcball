from odoo import api, fields, models


class HelpdeskTicket(models.Model):
    _name = 'buz.helpdesk.ticket'
    _description = 'Helpdesk Ticket'
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(
        string='Ticket Number',
        required=True,
        readonly=True,
        copy=False,
        default='New',
    )
    subject = fields.Char(required=True)
    description = fields.Text()
    requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    assigned_user_id = fields.Many2one('res.users', string='Assigned To')
    category_id = fields.Many2one('buz.helpdesk.category', string='Category')
    team_id = fields.Many2one('buz.helpdesk.team', string='Team')
    stage_id = fields.Many2one(
        'buz.helpdesk.stage',
        string='Stage',
        required=True,
        default=lambda self: self.env['buz.helpdesk.stage'].search(
            [('active', '=', True)], order='sequence, id', limit=1
        ),
    )
    priority = fields.Selection(
        [
            ('0', 'Low'),
            ('1', 'Normal'),
            ('2', 'High'),
            ('3', 'Urgent'),
        ],
        default='1',
        required=True,
    )
    active = fields.Boolean(default=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.helpdesk.ticket'
                ) or 'New'
        return super().create(vals_list)
