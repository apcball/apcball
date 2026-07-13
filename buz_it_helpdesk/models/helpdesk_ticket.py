from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError


class HelpdeskTicket(models.Model):
    _name = "it.helpdesk.ticket"
    _description = "IT Helpdesk Ticket"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority_id desc, create_date desc"

    name = fields.Char(string="Ticket No", required=True, copy=False, readonly=True, default="New", index=True)
    subject = fields.Char(required=True, tracking=True)
    description = fields.Html()
    requester_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    department = fields.Char(string="Department")
    category_id = fields.Many2one("it.helpdesk.category", tracking=True, required=True, check_company=True)
    priority_id = fields.Many2one("it.helpdesk.priority", tracking=True, required=True, check_company=True)
    priority_code = fields.Selection(related="priority_id.code", string="Priority Code", readonly=True)
    stage_id = fields.Many2one("it.helpdesk.stage", tracking=True, required=True, index=True, check_company=True, default=lambda self: self._default_stage_id())
    assigned_to = fields.Many2one("res.users", string="Assigned To", tracking=True)
    follower_ids = fields.Many2many("res.users", string="Followers")
    created_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    due_date = fields.Datetime()
    sla_id = fields.Many2one("it.helpdesk.sla", string="SLA", readonly=True, check_company=True)
    sla_deadline = fields.Datetime(readonly=True, tracking=True)
    response_deadline = fields.Datetime(readonly=True, tracking=True)
    first_response_at = fields.Datetime(readonly=True, tracking=True)
    is_response_overdue = fields.Boolean(compute="_compute_is_response_overdue", search="_search_is_response_overdue")
    tag_ids = fields.Many2many("it.helpdesk.tag", string="Tags")
    source = fields.Selection(
        [("web", "Web"), ("email", "Email"), ("phone", "Phone"), ("manual", "Manual")],
        default="manual",
        required=True,
    )
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    branch_id = fields.Many2one("res.company", string="Company / Branch")
    is_overdue = fields.Boolean(compute="_compute_is_overdue", search="_search_is_overdue")
    active = fields.Boolean(default=True)

    @api.model
    def _get_stage_for_company(self, company, stage_name):
        return self.env["it.helpdesk.stage"].search(
            [("name", "=", stage_name), ("company_id", "in", [company.id, False])],
            order="company_id desc, sequence, id",
            limit=1,
        )

    @api.model
    def _default_stage_id(self):
        stage = self._get_stage_for_company(self.env.company, "New")
        return stage.id if stage else False
    @api.model
    def _get_requester_department_name(self, user):
        employee = user.employee_id
        if employee and employee.department_id:
            return employee.department_id.display_name
        return False

    @api.onchange("requester_id")
    def _onchange_requester_id(self):
        for ticket in self:
            ticket.department = ticket._get_requester_department_name(ticket.requester_id)

    @api.model_create_multi
    def create(self, vals_list):
        priority = self.env["it.helpdesk.priority"].search([("company_id", "=", self.env.company.id)], order="sequence", limit=1)
        for vals in vals_list:
            requester_id = vals.get("requester_id") or self.env.user.id
            requester = self.env["res.users"].browse(requester_id)
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("it.helpdesk.ticket") or "New"
            vals.setdefault("stage_id", self._default_stage_id())
            vals.setdefault("priority_id", priority.id)
            vals.setdefault("requester_id", requester_id)
            vals.setdefault("department", self._get_requester_department_name(requester))
        records = super().create(vals_list)
        records._apply_sla()
        return records

    def _ensure_agent(self):
        if not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("Only Helpdesk Agents and Managers can change ticket status.")

    def _check_stage_change(self, stage_id):
        self._ensure_agent()
        target_stage = self.env["it.helpdesk.stage"].browse(stage_id).exists()
        if not target_stage:
            raise UserError("The selected ticket stage does not exist.")
        for ticket in self:
            if ticket.stage_id == target_stage:
                continue
            in_progress = self._get_stage_for_company(ticket.company_id, "In Progress")
            if ticket.stage_id.is_closed and target_stage != in_progress:
                raise UserError("A closed or cancelled ticket can only be reopened to In Progress.")
            closed = self._get_stage_for_company(ticket.company_id, "Closed")
            if target_stage == closed:
                resolved = self._get_stage_for_company(ticket.company_id, "Resolved")
                if ticket.stage_id != resolved:
                    raise UserError("A ticket must be Resolved before it can be Closed.")
    def write(self, vals):
        if "stage_id" in vals:
            self._check_stage_change(vals["stage_id"])
        result = super().write(vals)
        if {"category_id", "priority_id", "company_id"} & set(vals):
            self._apply_sla()
        return result

    def _apply_sla(self):
        for ticket in self:
            if not ticket.category_id or not ticket.priority_id:
                continue
            sla = self.env["it.helpdesk.sla"].search(
                [
                    ("company_id", "=", ticket.company_id.id),
                    ("active", "=", True),
                    ("category_id", "in", [ticket.category_id.id, False]),
                    ("priority_id", "in", [ticket.priority_id.id, False]),
                ],
                order="category_id desc, priority_id desc, sequence",
                limit=1,
            )
            values = {"sla_id": sla.id or False, "response_deadline": False, "sla_deadline": False}
            if sla:
                now = fields.Datetime.now()
                values["response_deadline"] = now + timedelta(hours=sla.response_hours)
                values["sla_deadline"] = now + timedelta(hours=sla.resolution_hours)
            ticket.with_context(skip_sla=True).write(values)

    @api.depends("response_deadline", "first_response_at", "stage_id.is_closed")
    def _compute_is_response_overdue(self):
        now = fields.Datetime.now()
        for ticket in self:
            ticket.is_response_overdue = bool(
                ticket.response_deadline
                and not ticket.first_response_at
                and ticket.response_deadline < now
                and not ticket.stage_id.is_closed
            )

    @api.model
    def _search_is_response_overdue(self, operator, value):
        now = fields.Datetime.now()
        overdue_domain = [
            ("response_deadline", "!=", False),
            ("response_deadline", "<", now),
            ("first_response_at", "=", False),
            ("stage_id.is_closed", "=", False),
        ]
        not_overdue_domain = [
            "|",
            ("response_deadline", "=", False),
            "|",
            ("response_deadline", ">=", now),
            "|",
            ("first_response_at", "!=", False),
            ("stage_id.is_closed", "=", True),
        ]

        if operator in ("=", "=="):
            return overdue_domain if value else not_overdue_domain
        if operator == "!=":
            return not_overdue_domain if value else overdue_domain
        raise ValueError("Unsupported operator for is_response_overdue search")
    @api.depends("sla_deadline", "stage_id.is_closed")
    def _compute_is_overdue(self):
        now = fields.Datetime.now()
        for ticket in self:
            ticket.is_overdue = bool(ticket.sla_deadline and ticket.sla_deadline < now and not ticket.stage_id.is_closed)

    @api.model
    def _search_is_overdue(self, operator, value):
        now = fields.Datetime.now()
        overdue_domain = [
            ("sla_deadline", "!=", False),
            ("sla_deadline", "<", now),
            ("stage_id.is_closed", "=", False),
        ]
        not_overdue_domain = ["|", ("sla_deadline", "=", False), "|", ("sla_deadline", ">=", now), ("stage_id.is_closed", "=", True)]

        if operator in ("=", "=="):
            return overdue_domain if value else not_overdue_domain
        if operator == "!=":
            return not_overdue_domain if value else overdue_domain
        raise ValueError("Unsupported operator for is_overdue search")

    def message_post(self, **kwargs):
        self.ensure_one()
        message = super().message_post(**kwargs)
        if (
            not self.first_response_at
            and message.message_type == "comment"
            and self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent")
            and not self.env.context.get("skip_first_response")
        ):
            self.with_context(skip_first_response=True).write({"first_response_at": fields.Datetime.now()})
        return message
    def action_assign(self):
        self._ensure_agent()
        for ticket in self:
            if ticket.stage_id.is_closed:
                raise UserError("A closed or cancelled ticket cannot be assigned.")
            stage = self._get_stage_for_company(ticket.company_id, "Assigned")
            if not stage:
                raise UserError("The Assigned stage is not configured for this company.")
            ticket.write({"assigned_to": self.env.user.id, "stage_id": stage.id})

    def action_resolve(self):
        self._ensure_agent()
        for ticket in self:
            if ticket.stage_id.is_closed:
                raise UserError("A closed or cancelled ticket cannot be resolved.")
            stage = self._get_stage_for_company(ticket.company_id, "Resolved")
            if not stage:
                raise UserError("The Resolved stage is not configured for this company.")
            ticket.write({"stage_id": stage.id})

    def action_close(self):
        self._ensure_agent()
        for ticket in self:
            resolved = self._get_stage_for_company(ticket.company_id, "Resolved")
            if ticket.stage_id != resolved:
                raise UserError("A ticket must be Resolved before it can be Closed.")
            stage = self._get_stage_for_company(ticket.company_id, "Closed")
            if not stage:
                raise UserError("The Closed stage is not configured for this company.")
            ticket.write({"stage_id": stage.id})
    def action_reopen(self):
        self._ensure_agent()
        for ticket in self:
            if not ticket.stage_id.is_closed:
                raise UserError("Only closed or cancelled tickets can be reopened.")
            stage = self._get_stage_for_company(ticket.company_id, "In Progress")
            if not stage:
                raise UserError("The In Progress stage is not configured for this company.")
            ticket.write({"stage_id": stage.id})
