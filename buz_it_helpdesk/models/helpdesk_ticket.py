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
    assignee_ids = fields.Many2many("res.users", string="Additional Assignees", tracking=True)
    team_id = fields.Many2one("it.helpdesk.team", string="Helpdesk Team", tracking=True, check_company=True)
    created_date = fields.Datetime(default=fields.Datetime.now, readonly=True)
    due_date = fields.Datetime()
    sla_id = fields.Many2one("it.helpdesk.sla", string="SLA", readonly=True, check_company=True)
    sla_deadline = fields.Datetime(readonly=True, tracking=True)
    response_deadline = fields.Datetime(readonly=True, tracking=True)
    first_response_at = fields.Datetime(readonly=True, tracking=True)
    resolved_at = fields.Datetime(readonly=True, tracking=True)
    sla_paused_at = fields.Datetime(readonly=True, tracking=True)
    sla_paused_hours = fields.Float(readonly=True, tracking=True)
    sla_overdue_notified_at = fields.Datetime(readonly=True)
    first_response_hours = fields.Float(compute="_compute_metrics", store=True)
    resolution_hours_elapsed = fields.Float(compute="_compute_metrics", store=True)
    sla_compliant = fields.Boolean(compute="_compute_metrics", store=True)
    due_today = fields.Boolean(compute="_compute_due_today", search="_search_due_today")
    attachment_ids = fields.Many2many("ir.attachment", "it_helpdesk_ticket_attachment_rel", "ticket_id", "attachment_id", string="Attachments")
    knowledge_article_ids = fields.Many2many("it.helpdesk.knowledge.article", string="Knowledge Articles Used")
    suggested_article_ids = fields.Many2many("it.helpdesk.knowledge.article", compute="_compute_suggested_articles", string="Suggested Articles")
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
        stage = self._get_stage_for_company(self.env.company, "Draft")
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
            if not vals.get("team_id"):
                team = self.env["it.helpdesk.team"].search([( "company_id", "=", vals.get("company_id", self.env.company.id)), ("active", "=", True)], order="sequence, id", limit=1)
                vals["team_id"] = team.id
        records = super().create(vals_list)
        records._apply_sla()
        for ticket in records:
            if ticket.requester_id.partner_id:
                ticket.message_subscribe(partner_ids=[ticket.requester_id.partner_id.id])
        return records

    def _ensure_agent(self):
        if not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("Only Helpdesk Agents and Managers can change ticket status.")

    def _check_stage_change(self, stage_id):
        confirm_mode = self.env.context.get("helpdesk_confirm")
        if not confirm_mode:
            self._ensure_agent()
        target_stage = self.env["it.helpdesk.stage"].browse(stage_id).exists()
        if not target_stage:
            raise UserError("The selected ticket stage does not exist.")
        if confirm_mode and target_stage.name != "New":
            raise AccessError("A requester can only confirm a Draft ticket.")
        for ticket in self:
            if confirm_mode and (ticket.requester_id != self.env.user or ticket.stage_id.name != "Draft"):
                raise AccessError("Only the requester can confirm their own Draft ticket.")
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
        if not self.env.su and not self.env.context.get("helpdesk_confirm") and not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent"): 
            protected = {"requester_id", "department", "company_id", "branch_id", "team_id", "assigned_to", "assignee_ids", "stage_id", "sla_id", "sla_deadline", "response_deadline", "first_response_at", "resolved_at", "sla_paused_at", "sla_paused_hours", "sla_overdue_notified_at"}
            if protected.intersection(vals):
                raise AccessError("Requesters cannot change assignment, workflow, SLA, or company fields.")
        stage_updates = {}
        if "stage_id" in vals:
            target = self.env["it.helpdesk.stage"].browse(vals["stage_id"])
            now = fields.Datetime.now()
            for ticket in self:
                if target.name == "Pending User" and ticket.stage_id.name != "Pending User":
                    stage_updates[ticket.id] = {"sla_paused_at": now}
                elif ticket.stage_id.name == "Pending User" and target.name != "Pending User" and ticket.sla_paused_at:
                    paused = ticket._get_work_hours(ticket.sla_paused_at, now)
                    update = {"sla_paused_at": False, "sla_paused_hours": ticket.sla_paused_hours + paused}
                    calendar = ticket.company_id.resource_calendar_id
                    if calendar and paused:
                        if ticket.sla_deadline:
                            update["sla_deadline"] = calendar.plan_hours(paused, ticket.sla_deadline, compute_leaves=True)
                        if ticket.response_deadline and not ticket.first_response_at:
                            update["response_deadline"] = calendar.plan_hours(paused, ticket.response_deadline, compute_leaves=True)
                    stage_updates[ticket.id] = update
            self._check_stage_change(vals["stage_id"])
        if vals.get("stage_id"):
            target_stage = self.env["it.helpdesk.stage"].browse(vals["stage_id"])
            if target_stage.name == "Resolved":
                vals = dict(vals)
                vals.setdefault("resolved_at", fields.Datetime.now())
        result = super().write(vals)
        for ticket_id, update in stage_updates.items():
            super(HelpdeskTicket, self.browse(ticket_id).with_context(skip_sla=True)).write(update)
        if {"category_id", "priority_id", "company_id"} & set(vals):
            self._apply_sla()
        return result

    @api.depends("category_id", "subject")
    def _compute_suggested_articles(self):
        Article = self.env["it.helpdesk.knowledge.article"]
        for ticket in self:
            domain = [("state", "=", "published"), ("company_id", "in", [ticket.company_id.id, False])]
            if ticket.category_id:
                domain += [("category_id", "in", [ticket.category_id.id, False])]
            if ticket.subject:
                domain += [("name", "ilike", ticket.subject.split()[0])]
            ticket.suggested_article_ids = Article.search(domain, limit=5)

    @api.depends("create_date", "first_response_at", "resolved_at", "sla_deadline")
    def _compute_metrics(self):
        now = fields.Datetime.now()
        for ticket in self:
            start = ticket.create_date or now
            ticket.first_response_hours = ticket._get_work_hours(start, ticket.first_response_at) - ticket.sla_paused_hours if ticket.first_response_at else 0.0
            ticket.resolution_hours_elapsed = ticket._get_work_hours(start, ticket.resolved_at) - ticket.sla_paused_hours if ticket.resolved_at else 0.0
            ticket.sla_compliant = bool(ticket.sla_deadline and ticket.resolved_at and ticket.resolved_at <= ticket.sla_deadline)

    @api.depends("sla_deadline", "stage_id.is_closed")
    def _compute_due_today(self):
        today = fields.Date.context_today(self)
        for ticket in self:
            ticket.due_today = bool(ticket.sla_deadline and ticket.sla_deadline.date() == today and not ticket.stage_id.is_closed)

    @api.model
    def _search_due_today(self, operator, value):
        today = fields.Date.context_today(self)
        start = fields.Datetime.to_datetime(today)
        end = start + timedelta(days=1)
        domain = [("sla_deadline", ">=", start), ("sla_deadline", "<", end), ("stage_id.is_closed", "=", False)]
        return domain if ((operator in ("=", "==") and value) or (operator == "!=" and not value)) else ["!"] + domain

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
                calendar = ticket.company_id.resource_calendar_id
                if calendar:
                    values["response_deadline"] = calendar.plan_hours(sla.response_hours, now, compute_leaves=True)
                    values["sla_deadline"] = calendar.plan_hours(sla.resolution_hours, now, compute_leaves=True)
                else:
                    values["response_deadline"] = now + timedelta(hours=sla.response_hours)
                    values["sla_deadline"] = now + timedelta(hours=sla.resolution_hours)
            ticket.sudo().with_context(skip_sla=True).write(values)

    def _get_work_hours(self, start, end):
        self.ensure_one()
        calendar = self.company_id.resource_calendar_id
        if calendar and start and end and end > start:
            return calendar.get_work_hours_count(start, end, compute_leaves=True)
        return max((end - start).total_seconds() / 3600, 0) if start and end else 0.0

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
    @api.model
    def message_new(self, msg_dict, custom_values=None):
        values = dict(custom_values or {})
        values.update({"subject": msg_dict.get("subject") or "Email Helpdesk Ticket", "description": msg_dict.get("body") or "", "source": "email"})
        author = self.env["res.partner"].browse(msg_dict.get("author_id"))
        if author and author.user_ids:
            values["requester_id"] = author.user_ids[0].id
        return super().message_new(msg_dict, custom_values=values)

    @api.model
    def message_update(self, msg_dict, update_vals=None):
        values = dict(update_vals or {})
        values.pop("subject", None)
        return super().message_update(msg_dict, values)

    @api.model
    def _cron_check_sla(self):
        overdue = self.search([("is_overdue", "=", True), ("sla_overdue_notified_at", "=", False)])
        manager_group = self.env.ref("buz_it_helpdesk.group_it_helpdesk_manager", raise_if_not_found=False)
        for ticket in overdue:
            partners = ticket.team_id.member_ids.mapped("partner_id")
            if manager_group:
                partners |= manager_group.users.filtered(lambda user: ticket.company_id in user.company_ids).mapped("partner_id")
            ticket.message_post(body="SLA deadline exceeded. Please review and escalate this ticket.", partner_ids=partners.ids, subtype_xmlid="mail.mt_note")
            ticket.sudo().with_context(skip_sla=True).write({"sla_overdue_notified_at": fields.Datetime.now()})
    def action_confirm(self):
        for ticket in self:
            if ticket.requester_id != self.env.user:
                raise AccessError("Only the requester can confirm this ticket.")
            if ticket.stage_id.name != "Draft":
                raise UserError("Only Draft tickets can be confirmed.")
            stage = ticket._get_stage_for_company(ticket.company_id, "New")
            if not stage:
                raise UserError("The New stage is not configured for this company.")
            ticket.with_context(helpdesk_confirm=True).write({"stage_id": stage.id})

    def action_assign_automatically(self):
        self._ensure_agent()
        for ticket in self:
            users = ticket.team_id.member_ids
            if users:
                counts = {user: self.search_count([( "assigned_to", "=", user.id), ("stage_id.is_closed", "=", False)]) for user in users}
                assignee = min(counts, key=counts.get)
                ticket.write({"assigned_to": assignee.id, "assignee_ids": fields.Command.link(assignee.id)})

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
