from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class HelpdeskTicket(models.Model):
    _name = 'buz.helpdesk.ticket'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
    create_ticket_date = fields.Date(
        string='Create Ticket',
        readonly=True,
        copy=False,
        default=fields.Date.context_today,
    )
    closed_ticket_date = fields.Date(
        string='Closed Ticket',
        readonly=True,
        copy=False,
    )
    subject = fields.Char(required=True, tracking=True)
    description = fields.Text()
    attachment_ids = fields.Many2many(
        'ir.attachment',
        'buz_helpdesk_ticket_attachment_rel',
        'ticket_id',
        'attachment_id',
        string='Attachments',
    )
    requester_id = fields.Many2one(
        'res.users',
        string='Requester',
        required=True,
        default=lambda self: self.env.user,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company,
        index=True,
        readonly=True,
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
        tracking=True,
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
    team_id = fields.Many2one(
        'buz.helpdesk.team', string='Team', tracking=True,
    )
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
        tracking=True,
        default=lambda self: self.env.ref('buz_it_helpdesk.stage_draft'),
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
        tracking=True,
    )
    active = fields.Boolean(default=True)
    is_draft_stage = fields.Boolean(compute='_compute_is_draft_stage')
    is_closed_stage = fields.Boolean(compute='_compute_is_closed_stage')
    show_receive_button = fields.Boolean(compute='_compute_show_receive_button')
    show_pending_user_button = fields.Boolean(compute='_compute_workflow_buttons')
    show_resume_work_button = fields.Boolean(compute='_compute_workflow_buttons')
    show_resolve_button = fields.Boolean(compute='_compute_workflow_buttons')
    show_close_button = fields.Boolean(compute='_compute_show_close_button')
    is_editable = fields.Boolean(compute='_compute_is_editable')
    can_manage_assignment = fields.Boolean(compute='_compute_can_manage_assignment')

    @api.depends('category_id.type_ids')
    def _compute_show_category_type(self):
        for ticket in self:
            ticket.show_category_type = bool(ticket.category_id.type_ids)

    @api.depends('stage_id')
    def _compute_is_draft_stage(self):
        draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
        for ticket in self:
            ticket.is_draft_stage = ticket.stage_id == draft_stage

    @api.depends('stage_id')
    def _compute_is_closed_stage(self):
        closed_stage = self.env.ref('buz_it_helpdesk.stage_closed')
        for ticket in self:
            ticket.is_closed_stage = ticket.stage_id == closed_stage

    @api.depends('stage_id', 'assigned_user_id')
    @api.depends_context('uid')
    def _compute_show_receive_button(self):
        new_stage = self.env.ref('buz_it_helpdesk.stage_new')
        is_agent = self._is_support_agent()
        for ticket in self:
            ticket.show_receive_button = (
                is_agent and ticket.stage_id == new_stage
                and not ticket.assigned_user_id
            )

    @api.depends('stage_id', 'assigned_user_id')
    @api.depends_context('uid')
    def _compute_workflow_buttons(self):
        in_progress_stage = self.env.ref('buz_it_helpdesk.stage_in_progress')
        pending_user_stage = self.env.ref('buz_it_helpdesk.stage_pending_user')
        is_agent = self._is_support_agent()
        is_manager = self._is_helpdesk_manager()
        for ticket in self:
            can_work = is_manager or ticket.assigned_user_id == self.env.user
            ticket.show_pending_user_button = (
                is_agent and can_work and ticket.stage_id == in_progress_stage
            )
            ticket.show_resume_work_button = (
                is_agent and can_work and ticket.stage_id == pending_user_stage
            )
            ticket.show_resolve_button = (
                is_agent and can_work and ticket.stage_id == in_progress_stage
            )

    @api.depends('stage_id', 'assigned_user_id')
    @api.depends_context('uid')
    def _compute_show_close_button(self):
        resolved_stage = self.env.ref('buz_it_helpdesk.stage_resolved')
        is_manager = self._is_helpdesk_manager()
        for ticket in self:
            ticket.show_close_button = (
                ticket.stage_id == resolved_stage
                and (is_manager or ticket.assigned_user_id == self.env.user)
            )

    @api.depends('stage_id', 'assigned_user_id', 'requester_id')
    @api.depends_context('uid')
    def _compute_is_editable(self):
        is_manager = self._is_helpdesk_manager()
        draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
        for ticket in self:
            if is_manager:
                ticket.is_editable = True
            elif ticket.stage_id == draft_stage:
                ticket.is_editable = ticket.requester_id == self.env.user
            else:
                ticket.is_editable = (
                    self._is_support_agent()
                    and ticket.assigned_user_id == self.env.user
                )

    @api.depends_context('uid')
    def _compute_can_manage_assignment(self):
        can_manage = self._is_helpdesk_manager()
        for ticket in self:
            ticket.can_manage_assignment = can_manage

    def _is_support_agent(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        )

    def _is_helpdesk_manager(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        )

    def copy(self, default=None):
        default = dict(default or {})
        default.update({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_draft').id,
            'team_id': False,
            'assigned_user_id': False,
            'create_ticket_date': False,
            'closed_ticket_date': False,
            'company_id': self.env.company.id,
            'active': True,
        })
        return super().copy(default)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            is_manager = self._is_helpdesk_manager()
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'buz.helpdesk.ticket'
                ) or 'New'
            vals['stage_id'] = self.env.ref('buz_it_helpdesk.stage_draft').id
            vals['team_id'] = False
            vals['assigned_user_id'] = False
            vals['closed_ticket_date'] = False
            vals['company_id'] = self.env.company.id
            if not is_manager:
                vals['requester_id'] = self.env.uid
            requester = self.env['res.users'].browse(
                vals.get('requester_id') or self.env.uid
            )
            vals['department_id'] = (
                requester.employee_id.department_id.id
                if requester.exists() and requester.employee_id
                else False
            )
        return super().create(vals_list)

    def action_create_ticket(self):
        self.ensure_one()
        if (
            not self._is_helpdesk_manager()
            and self.requester_id != self.env.user
        ):
            raise UserError(_('Only the requester can submit this ticket.'))
        draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
        if self.stage_id != draft_stage:
            raise UserError(_('Only Draft tickets can be created.'))

        recipients = self.env['res.users'].search([
            ('active', '=', True),
            ('groups_id', 'in', self.env.ref(
                'buz_it_helpdesk.group_it_support_agent'
            ).id),
        ]) - self.requester_id
        if not recipients:
            raise UserError(_('No active IT Support Agent is available.'))

        new_stage = self.env.ref('buz_it_helpdesk.stage_new')
        self.with_context(buz_helpdesk_transition=True).write({
            'stage_id': new_stage.id,
            'create_ticket_date': fields.Date.context_today(self),
        })

        activity_type = self.env.ref('mail.mail_activity_data_todo')
        activity_model = self.env['mail.activity']
        existing_user_ids = set(activity_model.search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', activity_type.id),
            ('user_id', 'in', recipients.ids),
            ('date_done', '=', False),
        ]).mapped('user_id').ids)
        note = _(
            'A new IT Helpdesk ticket %(ticket)s was opened by %(requester)s.',
            ticket=self.display_name,
            requester=self.requester_id.display_name,
        )
        for user in recipients:
            if user.id in existing_user_ids:
                continue
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=user.id,
                summary=_('New IT Helpdesk Ticket'),
                note=note,
            )
        return True

    def action_close_ticket(self):
        self.ensure_one()
        if not self._is_support_agent():
            raise UserError(_('Only IT Support Agents can close tickets.'))
        resolved_stage = self.env.ref('buz_it_helpdesk.stage_resolved')
        if self.stage_id != resolved_stage:
            raise UserError(_('Only Resolved tickets can be Closed.'))
        if (
            not self._is_helpdesk_manager()
            and self.assigned_user_id != self.env.user
        ):
            raise UserError(_('Only the assigned agent can close this ticket.'))
        self.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_closed').id,
            'closed_ticket_date': fields.Date.context_today(self),
        })
        self.message_post(
            body=_('This ticket has been closed by %s.') % (
                self.env.user.display_name
            ),
            partner_ids=[self.requester_id.partner_id.id],
            subtype_xmlid='mail.mt_comment',
        )
        return True

    def _assert_assigned_agent_workflow(self):
        if not self._is_support_agent():
            raise UserError(_('Only IT Support Agents can change workflow.'))
        if not self._is_helpdesk_manager() and self.assigned_user_id.id != self.env.uid:
            raise UserError(_('Only the assigned agent can change workflow.'))

    def action_request_user(self):
        self.ensure_one()
        self._assert_assigned_agent_workflow()
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_in_progress'):
            raise UserError(_('Only In Progress tickets can wait for the User.'))
        self.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_pending_user').id,
        })
        self.message_post(
            body=_('This ticket is waiting for a response from the requester.'),
            partner_ids=[self.requester_id.partner_id.id],
            subtype_xmlid='mail.mt_comment',
        )
        return True

    def action_resume_work(self):
        self.ensure_one()
        self._assert_assigned_agent_workflow()
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_pending_user'):
            raise UserError(_('Only Pending User tickets can resume work.'))
        self.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
        })
        return True

    def action_mark_resolved(self):
        self.ensure_one()
        self._assert_assigned_agent_workflow()
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_in_progress'):
            raise UserError(_('Only In Progress tickets can be Resolved.'))
        self.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_resolved').id,
        })
        return True

    def action_receive_ticket(self):
        self.ensure_one()
        if not self._is_support_agent():
            raise UserError(_('Only IT Support Agents can receive tickets.'))
        self.env.cr.execute(
            'SELECT id FROM buz_helpdesk_ticket WHERE id = %s FOR UPDATE',
            (self.id,),
        )
        self.invalidate_recordset(['stage_id', 'assigned_user_id'])
        new_stage = self.env.ref('buz_it_helpdesk.stage_new')
        if self.stage_id != new_stage or self.assigned_user_id:
            raise UserError(_('This ticket has already been received.'))
        receiving_team = self.env['buz.helpdesk.team'].search([
            ('active', '=', True),
            ('user_ids', 'in', self.env.user.id),
        ], order='sequence, name', limit=1)
        if not receiving_team:
            raise UserError(_(
                'The receiving IT user must belong to an active Helpdesk Team.'
            ))
        self.with_context(buz_helpdesk_transition=True).write({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
            'assigned_user_id': self.env.user.id,
            'team_id': receiving_team.id,
        })

        notification_activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('activity_type_id', '=', self.env.ref(
                'mail.mail_activity_data_todo'
            ).id),
            ('summary', '=', _('New IT Helpdesk Ticket')),
            ('date_done', '=', False),
        ])
        if notification_activities:
            notification_activities.action_done()
        return True

    def _change_stage_from_kanban(self, stage):
        """Apply workflow rules when an IT user drags a ticket."""
        self.ensure_one()
        if not self._is_support_agent():
            raise UserError(_('Only IT Support Agents can change Stage.'))
        if self.stage_id == stage:
            return True

        draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
        new_stage = self.env.ref('buz_it_helpdesk.stage_new')
        in_progress_stage = self.env.ref('buz_it_helpdesk.stage_in_progress')
        pending_user_stage = self.env.ref('buz_it_helpdesk.stage_pending_user')
        resolved_stage = self.env.ref('buz_it_helpdesk.stage_resolved')
        closed_stage = self.env.ref('buz_it_helpdesk.stage_closed')

        if stage == new_stage:
            if self.stage_id == draft_stage:
                return self.action_create_ticket()
            raise UserError(_('Tickets can only move to New from Draft.'))

        if stage == in_progress_stage:
            if self.stage_id == new_stage:
                return self.action_receive_ticket()
            if self.stage_id == pending_user_stage:
                return self.action_resume_work()
            raise UserError(_('Only New or Pending User tickets can move to In Progress.'))

        if stage == pending_user_stage:
            return self.action_request_user()

        if stage == resolved_stage:
            return self.action_mark_resolved()

        if stage == closed_stage:
            return self.action_close_ticket()

        raise UserError(_('Invalid Helpdesk workflow transition.'))

    def write(self, vals):
        if self.env.context.get('buz_helpdesk_transition'):
            return super().write(vals)
        is_manager = self._is_helpdesk_manager()
        protected = {
            'stage_id', 'assigned_user_id', 'create_ticket_date',
            'closed_ticket_date', 'name', 'department_id', 'requester_id',
            'company_id',
        }
        if 'stage_id' in vals:
            stage = self.env['buz.helpdesk.stage'].browse(vals['stage_id']).exists()
            if not stage:
                raise ValidationError(_('A valid Stage is required.'))
            remaining_vals = dict(vals)
            remaining_vals.pop('stage_id')
            for ticket in self:
                ticket._change_stage_from_kanban(stage)
                if remaining_vals:
                    ticket.write(remaining_vals)
            return True
        if any(field in vals for field in protected - {'assigned_user_id'}):
            raise UserError(_('System-managed ticket fields cannot be edited.'))
        if ('assigned_user_id' in vals or 'team_id' in vals) and not is_manager:
            raise UserError(_('Only a Manager can change assignment.'))
        if not is_manager:
            draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
            for ticket in self:
                if (
                    ticket.stage_id != draft_stage
                    and ticket.assigned_user_id != self.env.user
                ):
                    raise UserError(
                        _('Only the assigned agent can edit this ticket.')
                    )
        return super().write(vals)

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
