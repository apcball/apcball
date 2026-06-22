from datetime import timedelta

from odoo import api, fields, models, _


class ITRequest(models.Model):
    _name = 'it.request'
    _description = 'IT Request'
    _order = 'priority desc, create_date desc'
    _rec_name = 'name'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    # ── Identity / Number ──────────────────────────────────────────
    name = fields.Char(
        string='Request Number',
        required=True, readonly=True, copy=False,
        default='New',
    )
    subject = fields.Char(string='Subject', required=True, tracking=True)
    description = fields.Text(string='Description', tracking=True)

    # ── Categorization ─────────────────────────────────────────────
    category_id = fields.Many2one(
        comodel_name='it.request.category',
        string='Category',
        tracking=True,
    )
    sub_category_id = fields.Many2one(
        comodel_name='it.request.sub.category',
        string='Sub-Category',
        tracking=True,
        domain="[('category_id', '=', category_id)]",
    )
    request_type = fields.Selection(
        selection=[
            ('problem', 'Report Problem / แจ้งปัญหา'),
            ('feature_request', 'Feature Request / ขอเพิ่ม'),
            ('it_equipment_purchase', 'IT Equipment Purchase / ขอซื้ออุปกรณ์ IT'),
            ('it_equipment_repair', 'IT Equipment Repair / แจ้งซ่อม'),
        ],
        string='Request Type',
        required=True,
        default='problem',
        tracking=True,
    )
    module_name = fields.Char(
        string='Module',
        help='Name of the Odoo module related to this request',
        tracking=True,
    )

    # ── Priority / Impact / Urgency ────────────────────────────────
    priority = fields.Selection(
        selection=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('critical', 'Critical'),
        ],
        string='Priority',
        default='medium',
        tracking=True,
    )
    impact = fields.Selection(
        selection=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        string='Impact',
        default='medium',
        tracking=True,
    )
    urgency = fields.Selection(
        selection=[
            ('low', 'Low'),
            ('medium', 'Medium'),
            ('high', 'High'),
            ('urgent', 'Urgent'),
        ],
        string='Urgency',
        default='medium',
        tracking=True,
    )

    # ── State / Workflow ───────────────────────────────────────────
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('submitted', 'Submitted'),
            ('in_progress', 'In Progress'),
            ('waiting', 'Waiting'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
        string='State',
        default='draft',
        tracking=True,
    )
    kanban_state = fields.Selection(
        selection=[
            ('normal', 'In Progress'),
            ('done', 'Ready for Review'),
            ('blocked', 'Blocked'),
        ],
        string='Kanban State',
        default='normal',
        tracking=True,
    )
    color = fields.Integer(string='Color Index')
    active = fields.Boolean(string='Active', default=True)

    # ── Requester (Employee) ───────────────────────────────────────
    requester_id = fields.Many2one(
        comodel_name='hr.employee',
        string='Requester',
        required=True,
        tracking=True,
    )
    department_id = fields.Many2one(
        comodel_name='hr.department',
        string='Department',
        tracking=True,
    )
    work_location_id = fields.Many2one(
        comodel_name='hr.work.location',
        string='Work Location',
        compute='_compute_requester_info',
        store=True,
    )
    requester_phone = fields.Char(
        string='Phone',
        compute='_compute_requester_info',
        store=True,
    )
    requester_email = fields.Char(
        string='Email',
        compute='_compute_requester_info',
        store=True,
    )

    # ── Assignment ─────────────────────────────────────────────────
    team_id = fields.Many2one(
        comodel_name='it.request.team',
        string='IT Team',
        tracking=True,
    )
    assigned_to_id = fields.Many2one(
        comodel_name='res.users',
        string='Assigned To',
        tracking=True,
    )

    # ── Dates / SLA ────────────────────────────────────────────────
    create_date = fields.Datetime(string='Created On', readonly=True)
    response_date = fields.Datetime(string='Response Date', readonly=True, tracking=True)
    close_date = fields.Datetime(string='Close Date', readonly=True, tracking=True)
    resolution_date = fields.Datetime(string='Resolution Date', readonly=True, tracking=True)
    sla_deadline = fields.Datetime(string='SLA Deadline', tracking=True)
    sla_state = fields.Selection(
        selection=[
            ('on_track', 'On Track'),
            ('at_risk', 'At Risk'),
            ('breached', 'Breached'),
        ],
        string='SLA State',
        compute='_compute_sla_state',
        store=True,
    )

    # ── Resolution ─────────────────────────────────────────────────
    resolution_notes = fields.Text(string='Resolution Notes', tracking=True)

    # ── Images ─────────────────────────────────────────────────────
    image_ids = fields.One2many(
        comodel_name='it.request.image',
        inverse_name='it_request_id',
        string='Images',
    )

    # ═══════════════════════════════════════════════════════════════
    # COMPUTE
    # ═══════════════════════════════════════════════════════════════

    @api.depends('requester_id')
    def _compute_requester_info(self):
        for rec in self:
            if rec.requester_id:
                rec.department_id = rec.requester_id.department_id
                rec.work_location_id = rec.requester_id.work_location_id
                rec.requester_phone = rec.requester_id.work_phone or rec.requester_id.mobile_phone
                rec.requester_email = rec.requester_id.work_email
            else:
                rec.department_id = False
                rec.work_location_id = False
                rec.requester_phone = False
                rec.requester_email = False

    @api.depends('sla_deadline', 'state')
    def _compute_sla_state(self):
        now = fields.Datetime.now()
        for rec in self:
            if rec.state in ('done', 'cancel'):
                rec.sla_state = False
            elif not rec.sla_deadline:
                rec.sla_state = False
            elif now > rec.sla_deadline:
                rec.sla_state = 'breached'
            elif rec.sla_deadline - now < timedelta(hours=4):
                rec.sla_state = 'at_risk'
            else:
                rec.sla_state = 'on_track'

    # ═══════════════════════════════════════════════════════════════
    # ONCHANGE
    # ═══════════════════════════════════════════════════════════════

    @api.onchange('requester_id')
    def _onchange_requester_id(self):
        if self.requester_id:
            self.department_id = self.requester_id.department_id.id
        else:
            self.department_id = False

    @api.onchange('category_id')
    def _onchange_category_id(self):
        if self.sub_category_id.category_id != self.category_id:
            self.sub_category_id = False

    # ═══════════════════════════════════════════════════════════════
    # CRUD
    # ═══════════════════════════════════════════════════════════════

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = (
                    self.env['ir.sequence'].next_by_code('it.request.sequence') or 'New'
                )
            # Auto-set requester from current user's employee
            if not vals.get('requester_id'):
                employee = self.env.user.employee_id
                if employee:
                    vals['requester_id'] = employee.id
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('state') == 'done' and not vals.get('close_date'):
            vals['close_date'] = fields.Datetime.now()
            vals['resolution_date'] = fields.Datetime.now()
        if vals.get('state') in ('draft', 'submitted') and vals.get('close_date'):
            vals['close_date'] = False
            vals['resolution_date'] = False
        return super().write(vals)

    # ═══════════════════════════════════════════════════════════════
    # SLA HELPERS
    # ═══════════════════════════════════════════════════════════════

    def _get_sla_hours(self):
        """Return SLA hours based on priority."""
        mapping = {
            'critical': 4,
            'high': 24,
            'medium': 72,
            'low': 168,
        }
        return {rec.id: mapping.get(rec.priority, 72) for rec in self}

    def _set_sla_deadline(self):
        """Compute and set SLA deadline from create_date + priority hours."""
        sla_hours = self._get_sla_hours()
        now = fields.Datetime.now()
        for rec in self:
            hours = sla_hours.get(rec.id, 72)
            base_time = rec.create_date or now
            rec.sla_deadline = base_time + timedelta(hours=hours)

    # ═══════════════════════════════════════════════════════════════
    # WORKFLOW ACTIONS
    # ═══════════════════════════════════════════════════════════════

    def action_submit(self):
        self.state = 'submitted'
        self._set_sla_deadline()
        for rec in self:
            rec.message_post(body=_('Request %s has been submitted.') % rec.name)

    def action_assign_to_me(self):
        self.write({'assigned_to_id': self.env.user.id, 'state': 'in_progress'})
        for rec in self:
            if not rec.response_date:
                rec.response_date = fields.Datetime.now()
            rec.message_post(
                body=_('Request %s assigned to %s.') % (rec.name, self.env.user.name)
            )

    def action_in_progress(self):
        self.state = 'in_progress'
        for rec in self:
            if not rec.response_date:
                rec.response_date = fields.Datetime.now()

    def action_waiting(self):
        self.state = 'waiting'

    def action_done(self):
        self.state = 'done'
        for rec in self:
            rec.resolution_date = fields.Datetime.now()
            rec.message_post(body=_('Request %s has been completed.') % rec.name)

    def action_cancel(self):
        self.state = 'cancel'
        for rec in self:
            rec.message_post(body=_('Request %s has been cancelled.') % rec.name)

    def action_draft(self):
        self.write({
            'state': 'draft',
            'close_date': False,
            'resolution_date': False,
            'response_date': False,
            'sla_deadline': False,
        })
