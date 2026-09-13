import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import html2plaintext


_logger = logging.getLogger(__name__)
RESOLUTION_CONFIRMATION_SUMMARY = 'Confirm IT Resolution'
APPROVAL_ACTIVITY_SUMMARY = 'Helpdesk Approval Request'
SLA_GROUPS = 'buz_it_helpdesk.group_it_support_agent'


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
    category_id = fields.Many2one(
        'buz.helpdesk.category', string='Category', required=True,
    )
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
        group_expand='_read_group_stage_ids',
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
    sla_start_at = fields.Datetime(
        string='SLA Started At', readonly=True, copy=False, groups=SLA_GROUPS,
    )
    sla_response_at = fields.Datetime(
        string='Response Completed At', readonly=True, copy=False,
        groups=SLA_GROUPS,
    )
    sla_resolution_at = fields.Datetime(
        string='Resolution Completed At', readonly=True, copy=False,
        groups=SLA_GROUPS,
    )
    sla_rule_id = fields.Many2one(
        'buz.helpdesk.sla.rule', string='SLA Rule', compute='_compute_sla',
        groups=SLA_GROUPS,
    )
    sla_response_deadline = fields.Datetime(
        string='Response Deadline', compute='_compute_sla', groups=SLA_GROUPS,
    )
    sla_resolution_deadline = fields.Datetime(
        string='Resolution Deadline', compute='_compute_sla', groups=SLA_GROUPS,
    )
    sla_status = fields.Selection([
        ('on_track', 'On Track'), ('paused', 'Paused'),
        ('overdue', 'Overdue'), ('resolved', 'Resolved'),
        ('no_sla', 'No SLA'),
    ], string='SLA Status', compute='_compute_sla', groups=SLA_GROUPS)
    approval_state = fields.Selection(
        [
            ('none', 'No Approval'),
            ('pending', 'Pending Approval'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
        ],
        string='Approval Status',
        default='none',
        required=True,
        tracking=True,
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_manager_id = fields.Many2one(
        'res.users',
        string='Approval Manager',
        tracking=True,
        domain="[('id', 'in', approval_manager_domain_ids)]",
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_manager_domain_ids = fields.Many2many(
        'res.users',
        compute='_compute_approval_manager_domain_ids',
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_requested_by = fields.Many2one(
        'res.users', string='Requested By', readonly=True,
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_requested_at = fields.Datetime(
        string='Requested At', readonly=True,
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_decided_by = fields.Many2one(
        'res.users', string='Decided By', readonly=True,
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_decided_at = fields.Datetime(
        string='Decided At', readonly=True,
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_rejection_reason = fields.Text(
        string='Rejection Reason', readonly=True,
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    approval_request_note = fields.Text(
        string='Approval Request Note',
        groups='buz_it_helpdesk.group_it_support_agent',
    )
    active = fields.Boolean(default=True)
    is_draft_stage = fields.Boolean(compute='_compute_is_draft_stage')
    is_closed_stage = fields.Boolean(compute='_compute_is_closed_stage')
    show_receive_button = fields.Boolean(compute='_compute_show_receive_button')
    show_pending_user_button = fields.Boolean(compute='_compute_workflow_buttons')
    show_resume_work_button = fields.Boolean(compute='_compute_workflow_buttons')
    show_resolve_button = fields.Boolean(compute='_compute_workflow_buttons')
    show_close_button = fields.Boolean(compute='_compute_show_close_button')
    show_confirm_resolution_button = fields.Boolean(
        compute='_compute_show_confirm_resolution_button',
    )
    is_editable = fields.Boolean(compute='_compute_is_editable')
    can_edit_category_priority = fields.Boolean(
        compute='_compute_can_edit_category_priority',
    )
    can_manage_assignment = fields.Boolean(compute='_compute_can_manage_assignment')
    show_contact_line_button = fields.Boolean(
        compute='_compute_show_contact_line_button',
    )
    show_line_connection_shortcut = fields.Boolean(
        compute='_compute_show_line_connection_shortcut',
    )
    show_send_approval_button = fields.Boolean(
        compute='_compute_approval_buttons',
    )
    show_approve_button = fields.Boolean(
        compute='_compute_approval_buttons',
    )
    show_reject_button = fields.Boolean(
        compute='_compute_approval_buttons',
    )

    @api.model
    def _read_group_stage_ids(self, stages, domain, order):
        """Return active stages configured for display in Kanban.

        The Kanban renderer additionally filters groups that already contain
        tickets, because read_group includes existing groups even when they
        are not returned by group_expand.
        """
        return self.env['buz.helpdesk.stage'].search([
            ('active', '=', True),
            ('show_in_kanban', '=', True),
        ], order='sequence, name')

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

    @api.depends('stage_id', 'requester_id', 'category_id', 'priority')
    @api.depends_context('uid')
    def _compute_can_edit_category_priority(self):
        draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
        resolved_stage = self.env.ref('buz_it_helpdesk.stage_resolved')
        closed_stage = self.env.ref('buz_it_helpdesk.stage_closed')
        is_manager = self._is_helpdesk_manager()
        for ticket in self:
            if ticket.stage_id == draft_stage:
                ticket.can_edit_category_priority = (
                    is_manager or ticket.requester_id == self.env.user
                )
            else:
                ticket.can_edit_category_priority = (
                    is_manager
                    and (not ticket.category_id or not ticket.priority)
                    and ticket.stage_id not in (resolved_stage, closed_stage)
                )

    def _is_legacy_sla_setup_ticket(self):
        self.ensure_one()
        return not self.category_id or not self.priority

    def _can_manager_complete_legacy_sla_setup(self):
        self.ensure_one()
        return (
            self._is_helpdesk_manager()
            and self._is_legacy_sla_setup_ticket()
            and self.stage_id not in (
                self.env.ref('buz_it_helpdesk.stage_resolved'),
                self.env.ref('buz_it_helpdesk.stage_closed'),
            )
        )

    def _start_legacy_sla_if_ready(self):
        """Start from the repair time, never from the ticket create date."""
        self.ensure_one()
        if (
            self.sla_start_at
            or not self.category_id
            or not self.priority
            or self.stage_id in (
                self.env.ref('buz_it_helpdesk.stage_resolved'),
                self.env.ref('buz_it_helpdesk.stage_closed'),
            )
        ):
            return False
        started_at = fields.Datetime.now()
        vals = {'sla_start_at': started_at}
        if self.assigned_user_id or self.stage_id not in (
            self.env.ref('buz_it_helpdesk.stage_draft'),
            self.env.ref('buz_it_helpdesk.stage_new'),
        ):
            vals['sla_response_at'] = started_at
        self._write_workflow_fields(vals)
        return True

    @api.depends_context('uid')
    def _compute_can_manage_assignment(self):
        can_manage = self._is_helpdesk_manager()
        for ticket in self:
            ticket.can_manage_assignment = can_manage

    @api.depends('stage_id', 'assigned_user_id', 'requester_id')
    @api.depends_context('uid')
    def _compute_show_contact_line_button(self):
        in_progress = self.env.ref('buz_it_helpdesk.stage_in_progress')
        is_manager = self._is_helpdesk_manager()
        for ticket in self:
            ticket.show_contact_line_button = bool(
                ticket.stage_id == in_progress
                and ticket.requester_id
                and (is_manager or ticket.assigned_user_id == self.env.user)
            )

    @api.depends('stage_id', 'requester_id')
    @api.depends_context('uid')
    def _compute_show_confirm_resolution_button(self):
        resolved_stage = self.env.ref('buz_it_helpdesk.stage_resolved')
        for ticket in self:
            ticket.show_confirm_resolution_button = bool(
                ticket.stage_id == resolved_stage
                and ticket.requester_id == self.env.user
                and ticket._resolution_confirmation_activities()
            )

    @api.depends('requester_id')
    @api.depends_context('uid')
    def _compute_show_line_connection_shortcut(self):
        for ticket in self:
            ticket.show_line_connection_shortcut = (
                ticket.requester_id == self.env.user
            )

    @api.depends('stage_id', 'assigned_user_id', 'approval_state',
                 'approval_manager_id')
    @api.depends_context('uid')
    def _compute_approval_buttons(self):
        in_progress = self.env.ref('buz_it_helpdesk.stage_in_progress')
        is_manager = self._is_helpdesk_manager()
        is_agent = self._is_support_agent()
        for ticket in self:
            secure_ticket = ticket.sudo()
            can_request = is_manager or ticket.assigned_user_id == self.env.user
            ticket.show_send_approval_button = bool(
                is_agent
                and can_request
                and ticket.stage_id == in_progress
                and secure_ticket.approval_state in ('none', 'rejected')
                and secure_ticket.approval_manager_id
            )
            ticket.show_approve_button = bool(
                is_manager
                and secure_ticket.approval_state == 'pending'
                and secure_ticket.approval_manager_id == self.env.user
            )
            ticket.show_reject_button = ticket.show_approve_button

    @api.depends('company_id')
    def _compute_approval_manager_domain_ids(self):
        manager_group = self.env.ref(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        )
        for ticket in self:
            ticket.approval_manager_domain_ids = self.env['res.users'].search([
                ('active', '=', True),
                ('groups_id', 'in', manager_group.id),
                ('company_ids', 'in', ticket.company_id.id),
            ])

    def _is_support_agent(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_support_agent'
        )

    def _is_helpdesk_manager(self):
        return self.env.user.has_group(
            'buz_it_helpdesk.group_it_helpdesk_manager'
        )

    def _can_read_helpdesk_attachments(self):
        """ตรวจสิทธิ์อ่านไฟล์แนบตามสิทธิ์การอ่าน Ticket ปัจจุบัน"""
        self.ensure_one()
        if (
            self.env.user.has_group('buz_it_helpdesk.group_it_requester')
            and not self._is_support_agent()
            and not self._is_helpdesk_manager()
            and self.requester_id != self.env.user
        ):
            return False
        self.check_access_rights('read')
        self.check_access_rule('read')
        return True

    def _can_manage_helpdesk_attachments(self):
        """ตรวจสิทธิ์เพิ่ม/ลบไฟล์แนบตามสิทธิ์แก้ไข Ticket ปัจจุบัน"""
        self.ensure_one()
        if self._is_helpdesk_manager():
            return True
        draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
        if self.stage_id == draft_stage:
            return (
                self.env.user.has_group('buz_it_helpdesk.group_it_requester')
                and self.requester_id == self.env.user
            )
        return (
            self._is_support_agent()
            and self.assigned_user_id == self.env.user
        )

    def _check_helpdesk_attachment_write(self):
        """ป้องกันการแก้ไขไฟล์แนบโดยข้ามกฎการแก้ไข Ticket"""
        for ticket in self:
            if not ticket._can_manage_helpdesk_attachments():
                raise UserError(_(
                    'You do not have permission to manage attachments on this ticket.'
                ))

    def _get_sla_config(self):
        self.ensure_one()
        return self.env['buz.helpdesk.sla.config'].search([
            ('company_id', '=', self.company_id.id), ('active', '=', True),
        ], limit=1)

    def _get_sla_rule(self, config=None):
        self.ensure_one()
        config = config or self._get_sla_config()
        if not config:
            return self.env['buz.helpdesk.sla.rule']
        rules = config.rule_ids.filtered(
            lambda rule: rule.active and (
                not rule.category_id or rule.category_id == self.category_id
            ) and (
                not rule.priority or rule.priority == self.priority
            )
        )
        return min(
            rules,
            key=lambda rule: (-rule.specificity(), rule.sequence, rule.id),
            default=self.env['buz.helpdesk.sla.rule'],
        )

    @api.depends(
        'category_id', 'priority', 'company_id', 'stage_id', 'approval_state',
        'sla_start_at', 'sla_response_at', 'sla_resolution_at',
    )
    def _compute_sla(self):
        now = fields.Datetime.now()
        closed_stage = self.env.ref('buz_it_helpdesk.stage_closed')
        pending_user_stage = self.env.ref('buz_it_helpdesk.stage_pending_user')
        for ticket in self:
            ticket.sla_rule_id = False
            ticket.sla_response_deadline = False
            ticket.sla_resolution_deadline = False
            ticket.sla_status = 'no_sla'
            config = ticket._get_sla_config()
            rule = ticket._get_sla_rule(config)
            if (
                not config
                or not config._is_valid_for_calculation()
                or not rule
                or not ticket.sla_start_at
            ):
                continue
            ticket.sla_rule_id = rule
            ticket.sla_response_deadline = config.add_business_minutes(
                ticket.sla_start_at, rule.minutes('response'),
            )
            ticket.sla_resolution_deadline = config.add_business_minutes(
                ticket.sla_start_at, rule.minutes('resolution'),
            )
            if ticket.stage_id == closed_stage \
                    or ticket.sla_resolution_at:
                ticket.sla_status = 'resolved'
            elif ticket.stage_id == pending_user_stage \
                    or ticket.approval_state == 'pending':
                ticket.sla_status = 'paused'
            elif (
                (not ticket.sla_response_at and now > ticket.sla_response_deadline)
                or (not ticket.sla_resolution_at and now > ticket.sla_resolution_deadline)
            ):
                ticket.sla_status = 'overdue'
            else:
                ticket.sla_status = 'on_track'

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
            'approval_state': 'none',
            'approval_manager_id': False,
            'approval_requested_by': False,
            'approval_requested_at': False,
            'approval_decided_by': False,
            'approval_decided_at': False,
            'approval_rejection_reason': False,
            'approval_request_note': False,
            'sla_start_at': False,
            'sla_response_at': False,
            'sla_resolution_at': False,
        })
        return super().copy(default)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('category_id'):
                raise ValidationError(_('Category is required when creating a ticket.'))
            for field_name in (
                'approval_state', 'approval_manager_id',
                'approval_requested_by', 'approval_requested_at',
                'approval_decided_by', 'approval_decided_at',
                'approval_rejection_reason', 'approval_request_note',
            ):
                vals.pop(field_name, None)
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
        self._write_workflow_fields({
            'stage_id': new_stage.id,
            'create_ticket_date': fields.Date.context_today(self),
            'sla_start_at': fields.Datetime.now(),
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
        self._send_line_notification()
        return True

    def _approval_manager_is_valid(self):
        self.ensure_one()
        manager = self.approval_manager_id
        return bool(
            manager
            and manager.active
            and manager.company_ids & self.company_id
            and manager.has_group('buz_it_helpdesk.group_it_helpdesk_manager')
        )

    def _assert_can_request_approval(self):
        self.ensure_one()
        if not self._is_support_agent():
            raise UserError(_('Only IT Support Agents can request approval.'))
        if (
            not self._is_helpdesk_manager()
            and self.assigned_user_id != self.env.user
        ):
            raise UserError(_(
                'Only the assigned IT user or a Helpdesk Manager can request approval.'
            ))
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_in_progress'):
            raise UserError(_('Only In Progress tickets can request approval.'))
        if self.approval_state == 'pending':
            raise UserError(_('This ticket already has a pending approval request.'))
        if not self._approval_manager_is_valid():
            raise UserError(_(
                'Select an active Helpdesk Manager from the same company first.'
            ))

    def _approval_activities(self):
        self.ensure_one()
        return self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('user_id', '=', self.approval_manager_id.id),
            ('summary', '=', _(APPROVAL_ACTIVITY_SUMMARY)),
            ('date_done', '=', False),
        ])

    def action_send_to_approve(self):
        self.ensure_one()
        self._assert_can_request_approval()
        requested_at = fields.Datetime.now()
        self._write_approval_fields({
            'approval_state': 'pending',
            'approval_requested_by': self.env.user.id,
            'approval_requested_at': requested_at,
            'approval_decided_by': False,
            'approval_decided_at': False,
            'approval_rejection_reason': False,
        })
        note = self.approval_request_note or _(
            'Please review and decide the approval request for %s.'
        ) % self.display_name
        if not self._approval_activities():
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.approval_manager_id.id,
                summary=_(APPROVAL_ACTIVITY_SUMMARY),
                note=note,
            )
        self.message_post(
            body=_(
                'Approval requested from %(manager)s by %(requester)s.'
            ) % {
                'manager': self.approval_manager_id.display_name,
                'requester': self.env.user.display_name,
            },
            subtype_xmlid='mail.mt_note',
        )
        return True

    def _assert_can_decide_approval(self):
        self.ensure_one()
        if not self._is_helpdesk_manager():
            raise UserError(_('Only Helpdesk Managers can decide approval.'))
        if self.approval_state != 'pending':
            raise UserError(_('This ticket has no pending approval request.'))
        if self.approval_manager_id != self.env.user:
            raise UserError(_(
                'Only the selected Approval Manager can decide this request.'
            ))

    def action_approve(self):
        self.ensure_one()
        self._assert_can_decide_approval()
        self._approval_activities().action_done()
        self._write_approval_fields({
            'approval_state': 'approved',
            'approval_decided_by': self.env.user.id,
            'approval_decided_at': fields.Datetime.now(),
        })
        recipients = (
            [self.assigned_user_id.partner_id.id]
            if self.assigned_user_id else []
        )
        self.message_post(
            body=_(
                'Approval approved by %s. IT may continue work.'
            ) % self.env.user.display_name,
            partner_ids=recipients,
            subtype_xmlid='mail.mt_note',
        )
        return True

    def action_reject(self):
        self.ensure_one()
        self._assert_can_decide_approval()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Approval'),
            'res_model': 'buz.helpdesk.approval.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'view_id': self.env.ref(
                'buz_it_helpdesk.view_helpdesk_approval_reject_wizard'
            ).id,
            'context': {
                'default_ticket_id': self.id,
                'active_model': self._name,
                'active_ids': [self.id],
            },
        }

    def _reject_approval(self, reason):
        self.ensure_one()
        self._assert_can_decide_approval()
        reason = (reason or '').strip()
        if not reason:
            raise UserError(_('A rejection reason is required.'))
        self._approval_activities().action_done()
        self._write_approval_fields({
            'approval_state': 'rejected',
            'approval_decided_by': self.env.user.id,
            'approval_decided_at': fields.Datetime.now(),
            'approval_rejection_reason': reason,
        })
        recipients = (
            [self.assigned_user_id.partner_id.id]
            if self.assigned_user_id else []
        )
        self.message_post(
            body=_(
                'Approval rejected by %(manager)s. Reason: %(reason)s'
            ) % {
                'manager': self.env.user.display_name,
                'reason': reason,
            },
            partner_ids=recipients,
            subtype_xmlid='mail.mt_note',
        )
        return True

    def _send_line_notification(self):
        """Send LINE without allowing an external failure to roll back a Ticket."""
        self.ensure_one()
        try:
            return self.env[
                'buz.helpdesk.line.service'
            ].sudo()._send_ticket_notification(self)
        except Exception:
            _logger.exception(
                'LINE notification failed for Helpdesk Ticket %s; '
                'Ticket creation continues.',
                self.id,
            )
            return False

    def action_contact_user_via_line(self):
        self.ensure_one()
        if not self.show_contact_line_button:
            raise UserError(_(
                'Only the assigned IT user or a Helpdesk Manager can contact '
                'the requester while the ticket is In Progress.'
            ))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Contact User via LINE'),
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_model': self._name,
                'default_res_ids': [self.id],
                'default_partner_ids': [self.requester_id.partner_id.id],
                'default_composition_mode': 'comment',
                'buz_helpdesk_line_contact': True,
                'buz_helpdesk_ticket_id': self.id,
            },
        }

    def action_open_line_connection(self):
        self.ensure_one()
        if not self.show_line_connection_shortcut:
            raise UserError(_('Only the Requester can manage this connection.'))
        return {
            'type': 'ir.actions.client',
            'tag': 'buz_it_helpdesk.line_connection',
        }

    def action_send_line_message(self, body):
        self.ensure_one()
        if not self.show_contact_line_button:
            raise UserError(_('This ticket cannot be contacted via LINE.'))
        if not self.requester_id:
            raise UserError(_('This ticket has no Requester.'))
        line_service = self.env['buz.helpdesk.line.service'].sudo()
        line_user_id = line_service._parameter(
            line_service._user_key(self.requester_id.id)
        )
        if not line_user_id:
            raise UserError(_('The Requester has not connected a LINE account.'))
        text = html2plaintext(body or '').strip()
        if not text:
            raise UserError(_('Please enter a message.'))
        text = text[:1500]
        base_url = line_service._parameter('web.base.url').rstrip('/')
        ticket_url = '%s/web#id=%s&model=%s&view_type=form' % (
            base_url, self.id, self._name,
        )
        message = _(
            'IT Helpdesk Ticket %(ticket)s\n'
            'Subject: %(subject)s\n\n'
            '%(body)s\n\n'
            'Open in Odoo: %(url)s'
        ) % {
            'ticket': self.display_name,
            'subject': self.subject,
            'body': text,
            'url': ticket_url,
        }
        line_service._send_user_message(line_user_id, message)
        self.message_post(body=body, subtype_xmlid='mail.mt_comment')
        self._write_workflow_fields({
            'stage_id': self.env.ref(
                'buz_it_helpdesk.stage_pending_user'
            ).id,
        })
        self.activity_schedule(
            'mail.mail_activity_data_todo',
            user_id=self.requester_id.id,
            summary=_('Reply to IT Helpdesk Ticket'),
            note=_('Please reply to ticket %s in Odoo.') % self.display_name,
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
        if (
            not self._is_helpdesk_manager()
            and self._resolution_confirmation_activities()
        ):
            raise UserError(_(
                'The requester must confirm the resolution before this '
                'ticket can be closed.'
            ))
        self._write_workflow_fields({
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
        self._write_workflow_fields({
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
        self._write_workflow_fields({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
            'sla_response_at': fields.Datetime.now(),
        })
        return True

    def action_mark_resolved(self):
        self.ensure_one()
        self._assert_assigned_agent_workflow()
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_in_progress'):
            raise UserError(_('Only In Progress tickets can be Resolved.'))
        self._write_workflow_fields({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_resolved').id,
            'sla_resolution_at': fields.Datetime.now(),
        })
        self.message_post(
            body=_(
                'IT has marked this ticket as resolved. Please review the '
                'result and confirm the resolution before IT closes the ticket.'
            ),
            partner_ids=[self.requester_id.partner_id.id],
            subtype_xmlid='mail.mt_comment',
        )
        self.activity_schedule(
            'buz_it_helpdesk.mail_activity_type_resolution_confirmation',
            user_id=self.requester_id.id,
            summary=_(RESOLUTION_CONFIRMATION_SUMMARY),
            note=_(
                'Please review Ticket %s and confirm the resolution in Odoo.'
            ) % self.display_name,
        )
        self._send_resolution_line_notification()
        return True

    def _resolution_confirmation_activities(self):
        self.ensure_one()
        domain = [
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('user_id', '=', self.requester_id.id),
            ('date_done', '=', False),
        ]
        activity_type = self.env.ref(
            'buz_it_helpdesk.mail_activity_type_resolution_confirmation',
            raise_if_not_found=False,
        )
        if not activity_type:
            return self.env['mail.activity']

        activities = self.env['mail.activity'].search(
            domain + [('activity_type_id', '=', activity_type.id)]
        )
        # รองรับ Activity เดิมที่สร้างก่อนมีประเภทเฉพาะ โดยไม่ใช้ข้อความแปล
        # เป็นเงื่อนไขหลักของ Activity ใหม่อีกต่อไป
        legacy = self.env['mail.activity'].search(domain + [
            ('activity_type_id', '=', self.env.ref(
                'mail.mail_activity_data_todo'
            ).id),
            ('summary', 'in', [
                RESOLUTION_CONFIRMATION_SUMMARY,
                _(RESOLUTION_CONFIRMATION_SUMMARY),
            ]),
        ])
        return activities | legacy

    def _send_resolution_line_notification(self):
        self.ensure_one()
        line_service = self.env['buz.helpdesk.line.service'].sudo()
        line_user_id = line_service._parameter(
            line_service._user_key(self.requester_id.id)
        )
        if not line_user_id:
            _logger.info(
                'Requester %s has no LINE connection for resolved Ticket %s.',
                self.requester_id.id,
                self.id,
            )
            return False
        base_url = line_service._parameter('web.base.url').rstrip('/')
        ticket_url = '%s/web#id=%s&model=%s&view_type=form' % (
            base_url, self.id, self._name,
        )
        message = _(
            'IT Helpdesk Ticket %(ticket)s\n'
            'Subject: %(subject)s\n'
            'Status: Resolved\n\n'
            'Please review the result and confirm the resolution in Odoo.\n'
            'Open in Odoo: %(url)s'
        ) % {
            'ticket': self.display_name,
            'subject': self.subject,
            'url': ticket_url,
        }
        try:
            line_service._send_user_message(line_user_id, message)
            return True
        except Exception:
            _logger.exception(
                'LINE resolution notification failed for Helpdesk Ticket %s; '
                'the ticket remains Resolved.',
                self.id,
            )
            return False

    def action_confirm_resolution(self):
        self.ensure_one()
        if self.requester_id != self.env.user:
            raise UserError(_(
                'Only the requester can confirm this ticket resolution.'
            ))
        if self.stage_id != self.env.ref('buz_it_helpdesk.stage_resolved'):
            raise UserError(_('Only Resolved tickets can be confirmed.'))
        activities = self._resolution_confirmation_activities()
        if not activities:
            raise UserError(_(
                'There is no pending resolution confirmation for this ticket.'
            ))
        activities.action_done()
        self.message_post(
            body=_(
                'The requester confirmed that the resolution is complete. '
                'IT can now close this ticket.'
            ),
            partner_ids=(
                [self.assigned_user_id.partner_id.id]
                if self.assigned_user_id else []
            ),
            subtype_xmlid='mail.mt_comment',
        )
        if self.assigned_user_id:
            self.activity_schedule(
                'mail.mail_activity_data_todo',
                user_id=self.assigned_user_id.id,
                summary=_('Requester confirmed resolution'),
                note=_(
                    'The requester confirmed Ticket %s. You can close it.'
                ) % self.display_name,
            )
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
        self._write_workflow_fields({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
            'assigned_user_id': self.env.user.id,
            'team_id': receiving_team.id,
            'sla_response_at': fields.Datetime.now(),
        })
        self._complete_receive_activities()
        return True

    def _complete_receive_activities(self):
        """Complete the intake activities after a ticket is received."""
        self.ensure_one()

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

    def _complete_requester_activities(self):
        self.ensure_one()
        activities = self.env['mail.activity'].search([
            ('res_model', '=', self._name),
            ('res_id', '=', self.id),
            ('user_id', '=', self.requester_id.id),
            ('date_done', '=', False),
        ])
        if activities:
            activities.action_done()

    def message_post(self, *args, **kwargs):
        messages = super().message_post(*args, **kwargs)
        if self.env.context.get('buz_helpdesk_skip_reply_transition'):
            return messages
        author_id = kwargs.get('author_id') or self.env.user.partner_id.id
        pending = self.env.ref('buz_it_helpdesk.stage_pending_user')
        in_progress = self.env.ref('buz_it_helpdesk.stage_in_progress')
        for ticket in self:
            if (
                ticket.stage_id == pending
                and author_id == ticket.requester_id.partner_id.id
            ):
                ticket._complete_requester_activities()
                ticket._write_workflow_fields({'stage_id': in_progress.id})
                if ticket.assigned_user_id:
                    ticket.activity_schedule(
                        'mail.mail_activity_data_todo',
                        user_id=ticket.assigned_user_id.id,
                        summary=_('Requester replied'),
                        note=_('The requester replied to ticket %s.') % ticket.display_name,
                    )
        return messages

    def _auto_receive_assigned_ticket(self):
        """Start a New ticket when a manager completes its assignment."""
        self.ensure_one()
        self.env.cr.execute(
            'SELECT id FROM buz_helpdesk_ticket WHERE id = %s FOR UPDATE',
            (self.id,),
        )
        self.invalidate_recordset(['stage_id', 'team_id', 'assigned_user_id'])
        if (
            self.stage_id != self.env.ref('buz_it_helpdesk.stage_new')
            or not self.team_id
            or not self.assigned_user_id
        ):
            return False
        if self.assigned_user_id not in self.team_id.user_ids:
            raise ValidationError(_(
                'The assigned user must be a member of the selected team.'
            ))
        self._write_workflow_fields({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_in_progress').id,
            'sla_response_at': fields.Datetime.now(),
        })
        self._complete_receive_activities()
        return True

    def _rollback_to_new(self):
        """Return a mistakenly received ticket to the unassigned New queue."""
        self.ensure_one()
        if (
            not self._is_helpdesk_manager()
            and self.assigned_user_id != self.env.user
        ):
            raise UserError(_(
                'Only the assigned agent or a Helpdesk Manager can return '
                'this ticket to New.'
            ))
        self._write_workflow_fields({
            'stage_id': self.env.ref('buz_it_helpdesk.stage_new').id,
            'team_id': False,
            'assigned_user_id': False,
            'sla_response_at': False,
        })
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
            if self.stage_id == in_progress_stage:
                return self._rollback_to_new()
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

    def _write_workflow_fields(self, vals):
        """Write workflow-managed fields from trusted model methods only."""
        # ฟิลด์ SLA เป็นข้อมูลภายในและถูกจำกัดด้วย field groups แต่ผู้แจ้ง
        # ยังต้องเรียก action_create_ticket ได้ จึงเขียนผ่าน trusted sudo path
        # เดียวกับ workflow-managed fields เท่านั้น ไม่เปิดสิทธิ์ write ให้ผู้แจ้ง
        recordset = self.sudo()
        return super(HelpdeskTicket, recordset).write(vals)

    def _write_approval_fields(self, vals):
        """Write approval-managed fields from trusted model methods only."""
        recordset = self
        return super(HelpdeskTicket, recordset).write(vals)

    def write(self, vals):
        vals = dict(vals)
        if 'attachment_ids' in vals:
            self._check_helpdesk_attachment_write()
        is_manager = self._is_helpdesk_manager()
        is_requester_only = (
            self.env.user.has_group('buz_it_helpdesk.group_it_requester')
            and not self._is_support_agent()
        )
        protected = {
            'stage_id', 'assigned_user_id', 'create_ticket_date',
            'closed_ticket_date', 'name', 'department_id', 'requester_id',
            'company_id',
        }
        approval_protected = {
            'approval_state', 'approval_requested_by',
            'approval_requested_at', 'approval_decided_by',
            'approval_decided_at', 'approval_rejection_reason',
        }
        sla_protected = {
            'sla_start_at', 'sla_response_at', 'sla_resolution_at',
        }
        if sla_protected.intersection(vals):
            raise UserError(_(
                'SLA timing fields can only be changed through the workflow.'
            ))
        if approval_protected.intersection(vals):
            raise UserError(_(
                'Approval status and decision fields can only be changed '
                'through the approval workflow.'
            ))
        if is_requester_only and not is_manager:
            draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
            for ticket in self:
                if (
                    ticket.stage_id == draft_stage
                    and ticket.requester_id != self.env.user
                ):
                    raise UserError(_(
                        'A Requester can only edit their own Draft ticket.'
                    ))
        if {'category_id', 'priority'}.intersection(vals):
            draft_stage = self.env.ref('buz_it_helpdesk.stage_draft')
            for ticket in self:
                if ticket.stage_id == draft_stage:
                    continue
                if not ticket._can_manager_complete_legacy_sla_setup():
                    raise UserError(_(
                        'Category and Priority cannot be changed after the '
                        'ticket enters New.'
                    ))
                if 'category_id' in vals and not vals['category_id']:
                    raise ValidationError(_('Category cannot be cleared.'))
                if 'priority' in vals and not vals['priority']:
                    raise ValidationError(_('Priority cannot be cleared.'))
            if len(self) == 1 and not vals.get('priority') and not self.priority:
                vals['priority'] = '1'
        if 'approval_manager_id' in vals:
            for ticket in self:
                if ticket.approval_state not in ('none', 'rejected'):
                    raise UserError(_(
                        'The Approval Manager is locked while approval is pending '
                        'or completed.'
                    ))
                if not ticket._is_support_agent() or (
                    not is_manager and ticket.assigned_user_id != self.env.user
                ):
                    raise UserError(_(
                        'Only the assigned IT user or a Helpdesk Manager can '
                        'select an Approval Manager.'
                    ))
            manager_id = vals['approval_manager_id']
            if manager_id:
                manager = self.env['res.users'].browse(manager_id).exists()
                if not manager or not manager.active or not manager.has_group(
                    'buz_it_helpdesk.group_it_helpdesk_manager'
                ):
                    raise ValidationError(_(
                        'Approval Manager must be an active Helpdesk Manager.'
                    ))
                for ticket in self:
                    if ticket.company_id not in manager.company_ids:
                        raise ValidationError(_(
                            'Approval Manager must belong to the Ticket company.'
                        ))
        if 'approval_request_note' in vals:
            for ticket in self:
                if ticket.approval_state not in ('none', 'rejected'):
                    raise UserError(_(
                        'The approval request note is locked after submission.'
                    ))
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
        result = super().write(vals)
        if {'category_id', 'priority'}.intersection(vals):
            for ticket in self:
                ticket._start_legacy_sla_if_ready()
        if 'team_id' in vals or 'assigned_user_id' in vals:
            for ticket in self:
                ticket._auto_receive_assigned_ticket()
        return result

    def read(self, fields=None, load='_classic_read'):
        result = super().read(fields=fields, load=load)
        if fields is not None and 'attachment_ids' not in fields:
            return result
        attachment_model = self.env['ir.attachment']
        for values in result:
            attachment_ids = values.get('attachment_ids')
            if not attachment_ids:
                continue
            allowed = attachment_model.browse(attachment_ids)._helpdesk_allowed('read')
            values['attachment_ids'] = [
                attachment_id for attachment_id in attachment_ids
                if attachment_id in allowed.ids
            ]
        return result

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
