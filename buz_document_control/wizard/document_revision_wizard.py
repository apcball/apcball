from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class DocumentRevisionWizard(models.TransientModel):
    _name = "buz.document.revision.wizard"
    _description = "Create a document revision draft"

    document_id = fields.Many2one("buz.document", required=True, readonly=True)
    current_revision = fields.Char(related="document_id.current_revision", readonly=True)
    revision = fields.Char(string="New Revision", required=True)
    effective_date = fields.Date(required=True, default=fields.Date.context_today)
    review_date = fields.Date()
    original_file = fields.Binary(string="Upload New Document", required=True, attachment=False)
    original_filename = fields.Char()
    change_description = fields.Text(string="Description of Change", required=True)

    @api.model
    def default_get(self, field_names):
        values = super().default_get(field_names)
        document = self.env["buz.document"].browse(values.get("document_id"))
        document._check_manager()
        if document:
            document.check_access_rights("read")
            document.check_access_rule("read")
            current = document.current_revision_id
            if "revision" in field_names:
                values["revision"] = current._next_revision() if current else "00"
            if "review_date" in field_names:
                values["review_date"] = current.review_date if current else False
        return values

    def action_create_draft(self):
        self.ensure_one()
        document = self.document_id
        document._check_manager()
        document.check_access_rights("write")
        document.check_access_rule("write")
        if self.env["buz.document.revision"].search_count([("document_id", "=", document.id), ("revision", "=", self.revision)]):
            raise ValidationError(_("This revision already exists. Open the existing draft or choose another revision number."))
        # File validation, conversion and immutable publication rules remain on the existing model.
        revision = self.env["buz.document.revision"].create({
            "document_id": document.id, "revision": self.revision,
            "effective_date": self.effective_date, "review_date": self.review_date,
            "original_file": self.original_file, "original_filename": self.original_filename,
            "change_description": self.change_description,
        })
        return {"type": "ir.actions.client", "tag": "display_notification", "params": {
            "title": _("Draft created"), "message": _("Revision %s created successfully.", revision.revision),
            "type": "success", "next": {"type": "ir.actions.act_window", "name": _("Draft Revision"),
                "res_model": "buz.document.revision", "res_id": revision.id, "view_mode": "form", "views": [[False, "form"]], "target": "current"},
        }}
