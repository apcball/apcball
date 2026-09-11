from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


class BuzDocument(models.Model):
    _name = "buz.document"
    _description = "ISO Document Master"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "document_no"

    name = fields.Char(required=True, tracking=True)
    document_no = fields.Char(required=True, index=True, tracking=True)
    document_type_id = fields.Many2one("buz.document.type", tracking=True, ondelete="restrict")
    department_id = fields.Many2one("hr.department", tracking=True, ondelete="restrict")
    category_id = fields.Many2one("buz.document.category", ondelete="restrict")
    description = fields.Text()
    owner_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, ondelete="restrict")
    security_level = fields.Selection([
        ("general", "General"), ("restricted", "Restricted"), ("confidential", "Confidential")],
        default="general", required=True, tracking=True)
    allowed_group_ids = fields.Many2many("res.groups", "buz_document_group_rel", "document_id", "group_id", string="Allowed Groups")
    allowed_department_ids = fields.Many2many("hr.department", "buz_document_department_rel", "document_id", "department_id", string="Allowed Departments")
    allowed_employee_ids = fields.Many2many("hr.employee", "buz_document_employee_rel", "document_id", "employee_id", string="Allowed Employees")
    current_revision_id = fields.Many2one("buz.document.revision", readonly=True, copy=False, ondelete="restrict")
    current_revision = fields.Char(related="current_revision_id.revision", store=True)
    effective_date = fields.Date(related="current_revision_id.effective_date", store=True)
    review_date = fields.Date(related="current_revision_id.review_date", store=True)
    state = fields.Selection([( "draft", "Draft"), ("published", "Published"), ("obsolete", "Obsolete"), ("archived", "Archived")], default="draft", required=True, tracking=True)
    active = fields.Boolean(default=True)
    revision_ids = fields.One2many("buz.document.revision", "document_id")
    review_status = fields.Selection([( "ok", "OK"), ("due_soon", "Due Soon"), ("overdue", "Overdue")], compute="_compute_review_status", search="_search_review_status")

    _sql_constraints = [("document_no_uniq", "unique(document_no)", "Document number must be unique.")]

    @api.depends("review_date")
    def _compute_review_status(self):
        days = int(self.env["ir.config_parameter"].sudo().get_param("buz_document_control.review_warning_days", 30))
        today = fields.Date.today()
        for record in self:
            if not record.review_date or record.review_date > fields.Date.add(today, days=days):
                record.review_status = "ok"
            elif record.review_date < today:
                record.review_status = "overdue"
            else:
                record.review_status = "due_soon"

    def _search_review_status(self, operator, value):
        # Keep search semantics predictable in filters; computed per-record values are not SQL-searchable.
        today = fields.Date.today()
        days = int(self.env["ir.config_parameter"].sudo().get_param("buz_document_control.review_warning_days", 30))
        limit = fields.Date.add(today, days=days)
        if value == "overdue":
            domain = [("review_date", "<", today)]
        elif value == "due_soon":
            domain = [("review_date", ">=", today), ("review_date", "<=", limit)]
        else:  # ok: no review date set, or due date beyond the warning window
            domain = ["|", ("review_date", "=", False), ("review_date", ">", limit)]
        if operator in ("!=", "not in"):
            domain = ["!"] + domain
        return domain

    def action_new_revision(self):
        self.ensure_one()
        self._check_manager()
        self.check_access_rights("read")
        self.check_access_rule("read")
        return {
            "type": "ir.actions.act_window", "name": _("New Revision"),
            "res_model": "buz.document.revision.wizard", "view_mode": "form", "views": [[False, "form"]], "target": "new",
            "context": {"default_document_id": self.id},
        }

    def action_archive(self):
        self._check_manager()
        self.write({"active": False, "state": "archived"})

    def action_preview(self):
        self.ensure_one()
        if not self.current_revision_id:
            raise ValidationError(_("This document has no published revision to preview."))
        return self.current_revision_id.action_preview()

    def action_download(self):
        self.ensure_one()
        if not self.current_revision_id:
            raise ValidationError(_("This document has no published revision to download."))
        return self.current_revision_id.action_download()

    def _check_manager(self):
        if not self.env.user.has_group("buz_document_control.group_document_manager") and not self.env.user.has_group("buz_document_control.group_document_admin"):
            raise AccessError(_("Only Document Managers can perform this action."))
