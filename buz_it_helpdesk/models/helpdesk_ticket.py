from datetime import timedelta

from odoo import api, fields, models


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
    def _default_stage_id(self):
        stage = self.env.ref("buz_it_helpdesk.stage_new", raise_if_not_found=False)
        if not stage:
            stage = self.env["it.helpdesk.stage"].search(
                [("name", "=", "New"), ("company_id", "in", [self.env.company.id, False])],
                order="company_id desc, sequence, id",
                limit=1,
            )
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

    def write(self, vals):
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
            values = {"sla_id": sla.id or False, "sla_deadline": False}
            if sla:
                values["sla_deadline"] = fields.Datetime.now() + timedelta(hours=sla.resolution_hours)
            ticket.with_context(skip_sla=True).write(values)

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

    def action_assign(self):
        self.write({"assigned_to": self.env.user.id})
        assigned_stage = self.env["it.helpdesk.stage"].search([("name", "=", "Assigned")], limit=1)
        if assigned_stage:
            self.write({"stage_id": assigned_stage.id})

    def action_resolve(self):
        stage = self.env["it.helpdesk.stage"].search([("name", "=", "Resolved")], limit=1)
        if stage:
            self.write({"stage_id": stage.id})

    def action_close(self):
        stage = self.env["it.helpdesk.stage"].search([("name", "=", "Closed")], limit=1)
        if stage:
            self.write({"stage_id": stage.id})

    def action_reopen(self):
        stage = self.env["it.helpdesk.stage"].search([("name", "=", "In Progress")], limit=1)
        if stage:
            self.write({"stage_id": stage.id})
