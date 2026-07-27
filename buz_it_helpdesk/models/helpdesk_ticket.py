import base64
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class HelpdeskTicket(models.Model):
    _name = "it.helpdesk.ticket"
    _description = "IT Helpdesk Ticket"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority_id desc, create_date desc"
    _NEW_TICKET_ACTIVITY_SUMMARY = "New IT Helpdesk Ticket"
    _STAGE_CODE_BY_NAME = {
        "Draft": "draft",
        "New": "new",
        "In Progress": "in_progress",
        "Pending User": "pending_user",
        "Resolved": "resolved",
        "Closed": "closed",
        "Cancelled": "cancelled",
    }

    name = fields.Char(string="Ticket No", required=True, copy=False, readonly=True, default="New", index=True)
    subject = fields.Char(required=True, tracking=True)
    description = fields.Html()
    requester_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, tracking=True)
    department = fields.Char(string="Department")
    line_contact = fields.Char(string="Line Contact", tracking=True)
    category_id = fields.Many2one("it.helpdesk.category", tracking=True, required=True, check_company=True)
    priority_id = fields.Many2one("it.helpdesk.priority", tracking=True, required=True, check_company=True)
    priority_code = fields.Selection(related="priority_id.code", string="Priority Code", readonly=True)
    stage_id = fields.Many2one("it.helpdesk.stage", tracking=True, required=True, index=True, check_company=True, default=lambda self: self._default_stage_id())
    stage_code = fields.Selection(
        [
            ("draft", "Draft"),
            ("new", "New"),
            ("in_progress", "In Progress"),
            ("pending_user", "Pending User"),
            ("resolved", "Resolved"),
            ("closed", "Closed"),
            ("cancelled", "Cancelled"),
            ("other", "Other"),
        ],
        compute="_compute_stage_code",
        readonly=True,
    )
    assigned_to = fields.Many2one("res.users", string="Assigned To", tracking=True)
    assignee_ids = fields.Many2many("res.users", string="Additional Assignees", tracking=True)
    team_id = fields.Many2one("it.helpdesk.team", string="Helpdesk Team", tracking=True, check_company=True)
    team_member_ids = fields.Many2many("res.users", related="team_id.member_ids", string="Available Assignees", readonly=True)
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
    is_response_overdue = fields.Boolean(compute="_compute_is_response_overdue", search="_search_is_response_overdue")
    tag_ids = fields.Many2many("it.helpdesk.tag", string="Tags")
    source = fields.Selection(
        [("web", "Web"), ("email", "Email"), ("phone", "Phone"), ("manual", "Manual")],
        default="manual",
        required=True,
    )
    can_confirm = fields.Boolean(compute="_compute_can_confirm")
    can_assign_to_me = fields.Boolean(compute="_compute_can_assign_to_me")
    can_set_pending_user = fields.Boolean(compute="_compute_can_set_pending_user")
    can_resume_in_progress = fields.Boolean(compute="_compute_can_resume_in_progress")
    can_attach_files = fields.Boolean(compute="_compute_can_attach_files")
    can_edit_ticket = fields.Boolean(compute="_compute_can_edit_ticket")
    can_edit_protected_fields = fields.Boolean(compute="_compute_can_edit_protected_fields")
    company_id = fields.Many2one("res.company", default=lambda self: self.env.company, required=True, index=True)
    branch_id = fields.Many2one("res.company", string="Company / Branch")
    is_overdue = fields.Boolean(compute="_compute_is_overdue", search="_search_is_overdue")
    active = fields.Boolean(default=True)

    @api.depends("stage_id", "requester_id")
    def _compute_can_confirm(self):
        current_user = self.env.user
        is_requester = current_user.has_group("buz_it_helpdesk.group_it_helpdesk_requester")
        for ticket in self:
            ticket.can_confirm = is_requester and ticket._technical_stage_code(ticket.stage_id) == "draft" and ticket.requester_id == current_user

    @api.depends("stage_id")
    def _compute_can_assign_to_me(self):
        for ticket in self:
            ticket.can_assign_to_me = ticket._technical_stage_code(ticket.stage_id) == "new"

    @api.depends("stage_id")
    def _compute_can_set_pending_user(self):
        for ticket in self:
            ticket.can_set_pending_user = ticket._technical_stage_code(ticket.stage_id) == "in_progress"

    @api.depends("stage_id")
    def _compute_can_resume_in_progress(self):
        for ticket in self:
            ticket.can_resume_in_progress = ticket._technical_stage_code(ticket.stage_id) == "pending_user"

    @api.depends("stage_id")
    def _compute_can_attach_files(self):
        allowed_stages = {"Draft", "New", "In Progress", "Pending User"}
        for ticket in self:
            ticket.can_attach_files = ticket.stage_id.name in allowed_stages

    @api.depends("stage_id")
    def _compute_can_edit_ticket(self):
        is_agent = self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent")
        for ticket in self:
            ticket.can_edit_ticket = is_agent or not ticket.stage_id or ticket._technical_stage_code(ticket.stage_id) == "draft"
    @api.depends("stage_id")
    def _compute_can_edit_protected_fields(self):
        is_agent = self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent")
        for ticket in self:
            ticket.can_edit_protected_fields = is_agent

    @api.depends("stage_id", "stage_id.code", "stage_id.name")
    def _compute_stage_code(self):
        for ticket in self:
            ticket.stage_code = ticket._technical_stage_code(ticket.stage_id)

    def _technical_stage_code(self, stage):
        if not stage:
            return False
        return self._STAGE_CODE_BY_NAME.get(stage.name, "other") if stage.code == "other" else (stage.code or self._STAGE_CODE_BY_NAME.get(stage.name, "other"))

    @api.onchange("team_id")
    def _onchange_team_id_clear_assigned_to(self):
        for ticket in self:
            if ticket.assigned_to and ticket.assigned_to not in ticket.team_member_ids:
                ticket.assigned_to = False

    @api.constrains("assigned_to", "team_id")
    def _check_assigned_to_in_team(self):
        for ticket in self:
            if ticket.assigned_to and ticket.assigned_to not in ticket.team_member_ids:
                raise ValidationError("Assigned To must be a member of the selected Helpdesk Team.")
    @api.model
    def _get_stage_for_company(self, company, stage_name):
        return self.env["it.helpdesk.stage"].search(
            [("name", "=", stage_name), ("company_id", "in", [company.id, False])],
            order="company_id desc, sequence, id",
            limit=1,
        )

    @api.model
    def _default_stage_id(self, company=None):
        stage = self._get_stage_for_company(company or self.env.company, "Draft")
        return stage.id if stage else False

    @api.model
    def _default_priority_id(self, company=None):
        company = company or self.env.company
        priority = self.env["it.helpdesk.priority"].search(
            [("company_id", "=", company.id), ("active", "=", True)],
            order="sequence, id",
            limit=1,
        )
        return priority.id if priority else False

    @api.model
    def _default_team_id(self, company=None):
        company = company or self.env.company
        team = self.env["it.helpdesk.team"].search(
            [("company_id", "=", company.id), ("active", "=", True)],
            order="sequence, id",
            limit=1,
        )
        return team.id if team else False

    @api.model
    def _ensure_company_defaults(self, company=None):
        company = company or self.env.company
        stage_model = self.env["it.helpdesk.stage"].sudo().with_company(company)
        stages_by_name = {
            stage.name: stage
            for stage in stage_model.search([("company_id", "=", company.id)], order="sequence, id")
        }
        for name, code, sequence, is_closed in [
            ("Draft", "draft", 0, False),
            ("New", "new", 1, False),
            ("In Progress", "in_progress", 3, False),
            ("Pending User", "pending_user", 4, False),
            ("Resolved", "resolved", 5, False),
            ("Closed", "closed", 6, True),
            ("Cancelled", "cancelled", 7, True),
        ]:
            if name not in stages_by_name:
                stages_by_name[name] = stage_model.create(
                    {"name": name, "code": code, "sequence": sequence, "is_closed": is_closed, "company_id": company.id}
                )
        category_model = self.env["it.helpdesk.category"].sudo().with_company(company)
        category = category_model.search([("company_id", "=", company.id)], order="sequence, id", limit=1)
        if not category:
            category = category_model.create({"name": "Other", "company_id": company.id})
        priority_model = self.env["it.helpdesk.priority"].sudo().with_company(company)
        priority = priority_model.search([("company_id", "=", company.id)], order="sequence, id", limit=1)
        if not priority:
            priority = priority_model.create(
                {"name": "Medium", "code": "medium", "sequence": 2, "company_id": company.id}
            )
        team_model = self.env["it.helpdesk.team"].sudo().with_company(company)
        team = team_model.search([("company_id", "=", company.id), ("active", "=", True)], order="sequence, id", limit=1)
        if not team:
            team = team_model.create({"name": "IT Helpdesk", "sequence": 1, "company_id": company.id})
        sla_model = self.env["it.helpdesk.sla"].sudo().with_company(company)
        if not sla_model.search([("company_id", "=", company.id), ("active", "=", True)], limit=1):
            sla_model.create(
                {
                    "name": "Standard SLA",
                    "response_hours": 4,
                    "resolution_hours": 24,
                    "category_id": category.id,
                    "priority_id": priority.id,
                    "company_id": company.id,
                }
            )
        return True

    @api.model
    def _default_category_id(self, company=None):
        company = company or self.env.company
        category = self.env["it.helpdesk.category"].search(
            [("company_id", "=", company.id), ("active", "=", True)],
            order="sequence, name, id",
            limit=1,
        )
        return category.id if category else False

    @api.model
    def _validate_portal_selection(self, category_id, priority_id):
        try:
            category_id = int(category_id)
            priority_id = int(priority_id)
        except (TypeError, ValueError):
            raise ValidationError("Category and priority must be valid selections.")

        company = self.env.company
        category = self.env["it.helpdesk.category"].search(
            [("id", "=", category_id), ("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
        priority = self.env["it.helpdesk.priority"].search(
            [("id", "=", priority_id), ("company_id", "=", company.id), ("active", "=", True)],
            limit=1,
        )
        if not category or not priority:
            raise ValidationError("Category and priority must belong to the current company.")
        return category.id, priority.id

    @api.model
    def message_new(self, msg_dict, custom_values=None):
        vals = dict(custom_values or {})
        vals.setdefault("subject", msg_dict.get("subject") or "Email Helpdesk Ticket")
        vals.setdefault("description", msg_dict.get("body") or msg_dict.get("body_html") or False)
        vals.setdefault("source", "email")
        vals.setdefault("category_id", self._default_category_id())
        return self.create(vals).id

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
        requester_mode = not self.env.su and not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent")
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id") or self.env.company.id)
            self._ensure_company_defaults(company)
            if requester_mode:
                vals["stage_id"] = self._default_stage_id(company)
            requester_id = vals.get("requester_id") or self.env.user.id
            requester = self.env["res.users"].browse(requester_id)
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("it.helpdesk.ticket") or "New"
            vals.setdefault("stage_id", self._default_stage_id(company))
            vals.setdefault("category_id", self._default_category_id(company))
            vals.setdefault("priority_id", self._default_priority_id(company))
            vals.setdefault("requester_id", requester_id)
            vals.setdefault("department", self._get_requester_department_name(requester))
            if not vals.get("team_id"):
                team = self.env["it.helpdesk.team"].search([("id", "=", self._default_team_id(company)), ("active", "=", True)], limit=1)
                vals["team_id"] = team.id
        records = super().create(vals_list)
        records.filtered(lambda ticket: ticket._technical_stage_code(ticket.stage_id) != "draft")._apply_sla()
        for ticket in records:
            ticket._sync_responsible_notifications()
        return records

    def _get_responsible_users(self):
        self.ensure_one()
        return (self.requester_id | self.assigned_to | self.assignee_ids).filtered("active")

    def _get_notification_partners(self):
        self.ensure_one()
        return self._get_responsible_users().mapped("partner_id")

    def _sync_responsible_notifications(self, previous_users=None):
        self.ensure_one()
        current_users = self._get_responsible_users()
        previous_users = previous_users or self.env["res.users"]
        new_users = current_users - previous_users
        partners = new_users.mapped("partner_id")
        if partners:
            self.message_subscribe(partner_ids=partners.ids)
        activity_users = new_users - self.requester_id
        if self._technical_stage_code(self.stage_id) != "draft" and activity_users:
            self._schedule_new_ticket_activities(users=activity_users)

    def _add_uploaded_attachments(self, uploads):
        self.ensure_one()
        Attachment = self.env["ir.attachment"].sudo()
        attachments = self.env["ir.attachment"]
        for upload in uploads:
            if upload and upload.filename:
                attachment = Attachment.create({
                    "name": upload.filename,
                    "datas_fname": upload.filename,
                    "datas": base64.b64encode(upload.read()),
                    "res_model": self._name,
                    "res_id": self.id,
                    "type": "binary",
                    "company_id": self.company_id.id,
                })
                attachments |= attachment
        if attachments:
            self.sudo().write({"attachment_ids": [fields.Command.link(attachment.id) for attachment in attachments]})
        return attachments

    def _ensure_agent(self):
        if not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent"):
            raise AccessError("Only Helpdesk Agents and Managers can change ticket status.")

    def _schedule_new_ticket_activities(self, users=None):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        summary = self._NEW_TICKET_ACTIVITY_SUMMARY
        for ticket in self:
            ticket_users = users if users is not None else (ticket.team_member_ids | ticket.assigned_to | ticket.assignee_ids)
            ticket_users = ticket_users.filtered("active")
            existing_user_ids = ticket.activity_ids.filtered(
                lambda activity: activity.activity_type_id == activity_type
                and activity.summary == summary
            ).mapped("user_id").ids
            for member in ticket_users.filtered(lambda user: user.id not in existing_user_ids):
                ticket.sudo().activity_schedule(
                    "mail.mail_activity_data_todo",
                    user_id=member.id,
                    date_deadline=fields.Date.context_today(ticket),
                    summary=summary,
                    note="A new ticket from a user is waiting for the IT team.",
                )

    def action_clear_new_ticket_activity(self):
        activity_type = self.env.ref("mail.mail_activity_data_todo")
        activities = self.mapped("activity_ids").filtered(
            lambda activity: activity.user_id == self.env.user
            and activity.activity_type_id == activity_type
            and activity.summary == self._NEW_TICKET_ACTIVITY_SUMMARY
        )
        activities.unlink()
        return True

    def _check_stage_change(self, stage_id):
        confirm_mode = self.env.context.get("helpdesk_confirm")
        if not confirm_mode:
            self._ensure_agent()
        target_stage = self.env["it.helpdesk.stage"].browse(stage_id).exists()
        if not target_stage:
            raise UserError("The selected ticket stage does not exist.")
        target_code = self._technical_stage_code(target_stage)
        if confirm_mode and target_code != "new":
            raise AccessError("A requester can only confirm a Draft ticket.")
        allowed_transitions = {
            "draft": {"new", "cancelled"},
            "new": {"in_progress", "cancelled"},
            "in_progress": {"pending_user", "resolved", "cancelled"},
            "pending_user": {"in_progress", "cancelled"},
            "resolved": {"closed"},
            "closed": {"in_progress"},
            "cancelled": {"in_progress"},
        }
        for ticket in self:
            current_code = self._technical_stage_code(ticket.stage_id)
            if confirm_mode and (ticket.requester_id != self.env.user or current_code != "draft"):
                raise AccessError("Only the requester can confirm their own Draft ticket.")
            if current_code == target_code:
                continue
            if target_code not in allowed_transitions.get(current_code, set()):
                raise UserError(
                    "Invalid Helpdesk workflow transition: %s -> %s."
                    % (current_code, target_code)
                )

    def write(self, vals):
        is_agent = self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_agent")
        if not self.env.su and not is_agent:
            attachment_fields = {"attachment_ids", "message_main_attachment_id"}
            attachment_only = bool(vals) and set(vals) <= attachment_fields
            if attachment_only:
                allowed_stages = {"Draft", "New", "In Progress", "Pending User"}
                if any(ticket.stage_id.name not in allowed_stages for ticket in self):
                    raise AccessError("Attachments can only be added from Draft through Pending User.")
            else:
                if any(self._technical_stage_code(ticket.stage_id) != "draft" for ticket in self):
                    raise AccessError("Requesters cannot edit a confirmed ticket.")
                protected = {"stage_id", "requester_id", "sla_id", "sla_deadline", "response_deadline", "first_response_at", "resolved_at", "sla_paused_at", "sla_paused_hours", "sla_overdue_notified_at"}
                confirm_only_stage = self.env.context.get("helpdesk_confirm") and set(vals) <= {"stage_id"}
                if protected.intersection(vals) and not confirm_only_stage:
                    raise AccessError("Requesters cannot change assignment, workflow, SLA, or company fields.")
        stage_updates = {}
        previous_users_map = {}
        if {"assigned_to", "assignee_ids"} & set(vals):
            previous_users_map = {ticket.id: ticket._get_responsible_users() for ticket in self}
        if {"category_id", "priority_id"} & set(vals) and not self.env.context.get("sla_change_reason"):
            if any(self._technical_stage_code(ticket.stage_id) != "draft" for ticket in self):
                raise UserError("Changing Category or Priority after confirmation requires a SLA change reason.")
        if "stage_id" in vals:
            target = self.env["it.helpdesk.stage"].browse(vals["stage_id"])
            now = fields.Datetime.now()
            for ticket in self:
                if self._technical_stage_code(target) == "pending_user" and self._technical_stage_code(ticket.stage_id) != "pending_user":
                    stage_updates[ticket.id] = {"sla_paused_at": now}
                elif self._technical_stage_code(ticket.stage_id) == "pending_user" and self._technical_stage_code(target) != "pending_user" and ticket.sla_paused_at:
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
            if self._technical_stage_code(target_stage) == "resolved":
                vals = dict(vals)
                vals.setdefault("resolved_at", fields.Datetime.now())
        result = super().write(vals)
        for ticket_id, update in stage_updates.items():
            super(HelpdeskTicket, self.browse(ticket_id).with_context(skip_sla=True)).write(update)
        if {"assigned_to", "assignee_ids"} & set(vals):
            for ticket in self:
                ticket._sync_responsible_notifications(previous_users_map.get(ticket.id))
        if {"category_id", "priority_id", "company_id"} & set(vals):
            self.filtered(lambda ticket: ticket._technical_stage_code(ticket.stage_id) != "draft")._apply_sla()
        return result

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
        sla_model = self.env["it.helpdesk.sla"].sudo()
        for ticket in self:
            if not ticket.category_id or not ticket.priority_id:
                continue
            sla = sla_model.search(
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
            and message.subtype_id != self.env.ref("mail.mt_note")
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
        if not self.env.user.has_group("buz_it_helpdesk.group_it_helpdesk_requester"):
            raise AccessError("Only Helpdesk Requesters can confirm tickets.")
        for ticket in self:
            if ticket.requester_id != self.env.user:
                raise AccessError("Only the requester can confirm this ticket.")
            if self._technical_stage_code(ticket.stage_id) != "draft":
                raise UserError("Only Draft tickets can be confirmed.")
            stage = ticket._get_stage_for_company(ticket.company_id, "New")
            if not stage:
                raise UserError("The New stage is not configured for this company.")
            ticket.with_context(helpdesk_confirm=True).write({"stage_id": stage.id})
            ticket._apply_sla()
            ticket._schedule_new_ticket_activities()

    def action_assign_automatically(self):
        self._ensure_agent()
        for ticket in self:
            users = ticket.team_id.member_ids
            if users:
                counts = {user: self.search_count([( "assigned_to", "=", user.id), ("stage_id.is_closed", "=", False)]) for user in users}
                assignee = min(counts, key=counts.get)
                ticket.write({"assigned_to": assignee.id, "assignee_ids": fields.Command.link(assignee.id)})
                ticket.action_clear_new_ticket_activity()

    def action_assign(self):
        self._ensure_agent()
        for ticket in self:
            if ticket.stage_id.is_closed:
                raise UserError("A closed or cancelled ticket cannot be assigned.")
            if self.env.user not in ticket.team_member_ids:
                raise UserError("You must be a member of the selected Helpdesk Team to assign this ticket to yourself.")
            stage = self._get_stage_for_company(ticket.company_id, "In Progress")
            if not stage:
                raise UserError("The In Progress stage is not configured for this company.")
            ticket.write({"assigned_to": self.env.user.id, "stage_id": stage.id})
            ticket.action_clear_new_ticket_activity()

    def action_pending_user(self):
        self._ensure_agent()
        for ticket in self:
            if self._technical_stage_code(ticket.stage_id) != "in_progress":
                raise UserError("Only an In Progress ticket can be set to Pending User.")
            stage = self._get_stage_for_company(ticket.company_id, "Pending User")
            if not stage:
                raise UserError("The Pending User stage is not configured for this company.")
            ticket.write({"stage_id": stage.id})
    def action_in_progress(self):
        self._ensure_agent()
        for ticket in self:
            if self._technical_stage_code(ticket.stage_id) != "pending_user":
                raise UserError("Only a Pending User ticket can be returned to In Progress.")
            stage = self._get_stage_for_company(ticket.company_id, "In Progress")
            if not stage:
                raise UserError("The In Progress stage is not configured for this company.")
            ticket.write({"stage_id": stage.id})

    def action_resolve(self):
        self._ensure_agent()
        for ticket in self:
            if ticket.stage_id.is_closed:
                raise UserError("A closed or cancelled ticket cannot be resolved.")
            stage = self._get_stage_for_company(ticket.company_id, "Resolved")
            if not stage:
                raise UserError("The Resolved stage is not configured for this company.")
            ticket.write({"stage_id": stage.id})

    def action_cancel(self):
        self._ensure_agent()
        for ticket in self:
            if self._technical_stage_code(ticket.stage_id) not in {
                "draft",
                "new",
                "in_progress",
                "pending_user",
            }:
                raise UserError("Only open tickets can be cancelled.")
            stage = self._get_stage_for_company(ticket.company_id, "Cancelled")
            if not stage:
                raise UserError("The Cancelled stage is not configured for this company.")
            ticket.write({"stage_id": stage.id})

    def action_close(self):
        self._ensure_agent()
        for ticket in self:
            if self._technical_stage_code(ticket.stage_id) == "closed":
                raise UserError("A Closed ticket cannot be closed again.")
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
            if self._technical_stage_code(ticket.stage_id) not in {"closed", "cancelled"}:
                raise UserError("Only closed or cancelled tickets can be reopened.")
            stage = self._get_stage_for_company(ticket.company_id, "In Progress")
            if not stage:
                raise UserError("The In Progress stage is not configured for this company.")
            ticket.write(
                {
                    "stage_id": stage.id,
                    "resolved_at": False,
                    "sla_overdue_notified_at": False,
                    "sla_paused_at": False,
                    "sla_paused_hours": 0,
                }
            )
            ticket._apply_sla()
