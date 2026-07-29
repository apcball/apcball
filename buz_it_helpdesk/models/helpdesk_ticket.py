from odoo import api, fields, models
from odoo.exceptions import ValidationError


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
    department_id = fields.Many2one(
        'hr.department',
        string='Department',
        readonly=True,
        index=True,
    )
    assigned_user_id = fields.Many2one(
        'res.users',
        string='Assigned To',
        domain="[('id', 'in', team_user_ids)]",
    )
    category_id = fields.Many2one('buz.helpdesk.category', string='Category')
    category_type_id = fields.Many2one(
        'buz.helpdesk.category.type', string='Type',
        domain="[('id', 'in', category_type_ids)]",
    )
    category_type_ids = fields.One2many(
        'buz.helpdesk.category.type', 'category_id',
        related='category_id.type_ids',
        string='Category Types', readonly=True,
    )
    show_category_type = fields.Boolean(
        compute='_compute_show_category_type',
    )
    team_id = fields.Many2one('buz.helpdesk.team', string='Team')
    team_user_ids = fields.Many2many(
        'res.users',
        related='team_id.user_ids',
        string='Team Users',
        readonly=True,
    )
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

    @api.depends('category_id.name')
    def _compute_show_category_type(self):
        for ticket in self:
            ticket.show_category_type = ticket.category_id.name == 'Hardware'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.helpdesk.ticket'
                ) or 'New'
            requester = self.env['res.users'].browse(
                vals.get('requester_id') or self.env.uid
            )
            vals['department_id'] = (
                requester.employee_id.department_id.id
                if requester.exists() and requester.employee_id
                else False
            )
        return super().create(vals_list)

    @api.onchange('requester_id')
    def _onchange_requester_id(self):
        """Keep the ticket department aligned with its requester."""
        self.department_id = (
            self.requester_id.employee_id.department_id
            if self.requester_id and self.requester_id.employee_id
            else False
        )

    @api.onchange('team_id')
    def _onchange_team_id(self):
        """Clear an assignee who is not a member of the selected team."""
        if self.team_id and self.assigned_user_id not in self.team_id.user_ids:
            self.assigned_user_id = False

    @api.onchange('category_id')
    def _onchange_category_id(self):
        """Clear a type that does not belong to the selected category."""
        if (
            not self.show_category_type
            or (
                self.category_type_id
                and self.category_type_id not in self.category_id.type_ids
            )
        ):
            self.category_type_id = False

    @api.constrains('category_id', 'category_type_id')
    def _check_category_type(self):
        for ticket in self:
            if ticket.category_type_id and ticket.category_type_id.category_id != ticket.category_id:
                raise ValidationError(
                    'The selected type must belong to the selected category.'
                )

    @api.constrains('team_id', 'assigned_user_id')
    def _check_assigned_user_in_team(self):
        for ticket in self:
            if (
                ticket.team_id
                and ticket.assigned_user_id
                and ticket.assigned_user_id not in ticket.team_id.user_ids
            ):
                raise ValidationError(
                    'The assigned user must be a member of the selected team.'
                )
