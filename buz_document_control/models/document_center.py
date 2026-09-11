"""Presentation-only queries. Every document/revision query uses the caller's ACLs."""
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.osv import expression


DOCUMENT_FIELDS = [
    "document_no", "name", "document_type_id", "department_id", "category_id",
    "current_revision_id", "current_revision", "effective_date", "review_date",
    "review_status", "security_level", "state", "write_date", "original_filename",
]
REVISION_FIELDS = [
    "revision", "state", "effective_date", "review_date", "published_date",
    "published_by", "change_description", "original_filename", "preview_status",
]


class DocumentCenter(models.Model):
    _inherit = "buz.document"

    original_filename = fields.Char(
        related="current_revision_id.original_filename", compute_sudo=False,
    )
    is_my_department = fields.Boolean(compute="_compute_my_department", search="_search_my_department")

    @api.depends_context("uid")
    @api.depends("department_id")
    def _compute_my_department(self):
        departments = self.env.user.employee_ids.department_id
        for document in self:
            document.is_my_department = document.department_id in departments

    def _search_my_department(self, operator, value):
        if operator not in ("=", "!="):
            raise ValidationError(_("Unsupported department filter."))
        positive = bool(value) == (operator == "=")
        return [("department_id", "in" if positive else "not in", self.env.user.employee_ids.department_id.ids)]

    @api.model
    def _center_filters(self):
        published = [("state", "=", "published")]
        return {
            "all": [],
            "published": published,
            "forms": [("document_type_id.code", "=", "FM")],
            "my_department": [("is_my_department", "=", True)],
            "recent": [("write_date", ">=", fields.Datetime.subtract(fields.Datetime.now(), days=30))],
            "draft": [("state", "=", "draft")],
            "review": [("revision_ids.state", "=", "review")],
            "due": published + [("review_status", "=", "due_soon")],
            "overdue": published + [("review_status", "=", "overdue")],
            "confidential": [("security_level", "=", "confidential")],
            "preview_failed": [("current_revision_id.preview_status", "=", "failed")],
        }

    @api.model
    def get_document_center_data(self, query="", filter_key="all", type_id=False, offset=0, include_summary=True):
        self.check_access_rights("read")
        manager = self.env.user.has_group("buz_document_control.group_document_manager")
        filters = self._center_filters()
        if filter_key not in filters or (not manager and filter_key in ("draft", "review", "overdue", "confidential", "preview_failed")):
            filter_key = "all"
        base = [("state", "not in", ["obsolete", "archived"])]
        domain = expression.AND([base, filters[filter_key]])
        if type_id:
            domain = expression.AND([domain, [("document_type_id", "=", int(type_id))]])
        query = (query or "").strip()[:200]
        if query:
            search_fields = ["document_no", "name", "document_type_id.name", "document_type_id.code",
                             "department_id.name", "category_id.name", "current_revision"]
            domain = expression.AND([domain, expression.OR([[(name, "ilike", query)] for name in search_fields])])
        offset = max(0, int(offset))
        result = {
            "is_manager": manager, "domain": domain, "offset": offset, "limit": 12,
            "total": self.search_count(domain),
            "documents": self.search_read(domain, DOCUMENT_FIELDS, offset=offset, limit=12, order="write_date desc, id desc"),
        }
        if include_summary:
            groups = self.read_group(base, ["document_type_id"], ["document_type_id"])
            counts = {g["document_type_id"][0]: g["document_type_id_count"] for g in groups if g["document_type_id"]}
            result["document_types"] = [dict(row, count=counts.get(row["id"], 0)) for row in
                                        self.env["buz.document.type"].search_read([], ["code", "name"], limit=100)]
            result["counts"] = {
                key: self.search_count(expression.AND([base, filters[key]]))
                for key in (["all", "published", "draft", "review", "due", "overdue"] if manager else ["all"])
            }
            result["needs_attention"] = []
            if manager:
                attention_domain = expression.AND([base, expression.OR([
                    filters["due"], filters["overdue"], filters["preview_failed"], filters["draft"], filters["review"],
                ])])
                result["needs_attention"] = self.search_read(
                    attention_domain, DOCUMENT_FIELDS, limit=8, order="review_date asc, write_date desc",
                )
                revisions = self.env["buz.document.revision"].search_read(
                    [("state", "in", ["draft", "review"]), ("document_id", "in", [row["id"] for row in result["needs_attention"]])],
                    ["document_id", "state"], order="write_date desc, id desc", limit=80,
                )
                pending = {}
                for revision in revisions:
                    pending.setdefault(revision["document_id"][0], revision)
                for row in result["needs_attention"]:
                    row["pending_revision"] = pending.get(row["id"], False)
        return result

    def get_document_viewer_data(self):
        self.ensure_one()
        self.check_access_rights("read")
        self.check_access_rule("read")
        manager = self.env.user.has_group("buz_document_control.group_document_manager")
        document = self.read(DOCUMENT_FIELDS + ["description", "owner_id"])[0]
        revision_model = self.env["buz.document.revision"]
        current = revision_model.search_read(
            [("id", "=", self.current_revision_id.id)], REVISION_FIELDS, limit=1,
        )
        history_domain = [("document_id", "=", self.id)]
        history = revision_model.search_read(history_domain, REVISION_FIELDS, limit=50, order="revision_date desc, id desc")
        result = {
            "document": document, "current": current[0] if current else False,
            "history": history, "history_count": revision_model.search_count(history_domain),
            "is_manager": manager, "access": False, "activity": [],
        }
        if manager:
            result["access"] = {
                "groups": self.allowed_group_ids.mapped("display_name"),
                "departments": self.allowed_department_ids.mapped("display_name"),
            }
            result["activity"] = self.env["buz.document.download.log"].search_read(
                [("document_id", "=", self.id)], ["user_id", "revision_id", "action_type", "download_date"], limit=20,
            )
        return result

    def action_document_viewer(self):
        self.ensure_one()
        self.check_access_rights("read")
        self.check_access_rule("read")
        return {"type": "ir.actions.client", "tag": "buz_document_control.viewer",
                "name": _("Document Viewer"), "params": {"document_id": self.id}}
