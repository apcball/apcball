import base64
import os
import shutil
import subprocess
import tempfile

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


ALLOWED_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".txt", ".jpg", ".jpeg", ".png"}
CONVERTIBLE_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


class BuzDocumentRevision(models.Model):
    _name = "buz.document.revision"
    _description = "ISO Document Revision"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "document_id, revision_date desc, id desc"

    document_id = fields.Many2one("buz.document", required=True, ondelete="cascade", index=True)
    revision = fields.Char(required=True, tracking=True)
    revision_date = fields.Date(default=fields.Date.today, required=True)
    effective_date = fields.Date(tracking=True)
    review_date = fields.Date(tracking=True)
    expiration_date = fields.Date()
    change_description = fields.Text(required=True, tracking=True, default="Initial issue")
    state = fields.Selection([( "draft", "Draft"), ("review", "Review"), ("published", "Published"), ("obsolete", "Obsolete"), ("cancelled", "Cancelled")], default="draft", required=True, tracking=True)
    original_file = fields.Binary(attachment=True, copy=False)
    original_filename = fields.Char(copy=False)
    preview_file = fields.Binary(attachment=True, readonly=True, copy=False)
    preview_filename = fields.Char(readonly=True, copy=False)
    preview_status = fields.Selection([( "none", "None"), ("pending", "Pending"), ("ready", "Ready"), ("failed", "Failed")], default="none", readonly=True)
    preview_error = fields.Text(readonly=True, copy=False)
    created_by = fields.Many2one("res.users", related="create_uid", readonly=True)
    published_by = fields.Many2one("res.users", readonly=True, copy=False)
    published_date = fields.Datetime(readonly=True, copy=False)
    obsolete_by = fields.Many2one("res.users", readonly=True, copy=False)
    obsolete_date = fields.Datetime(readonly=True, copy=False)

    _sql_constraints = [("document_revision_uniq", "unique(document_id, revision)", "A document revision must be unique.")]

    @api.constrains("original_file", "original_filename")
    def _check_file(self):
        for record in self:
            if record.original_file:
                ext = os.path.splitext(record.original_filename or "")[1].lower()
                if ext not in ALLOWED_EXTENSIONS:
                    raise ValidationError(_("Unsupported file type. Please upload a supported document format."))
                try:
                    max_mb = float(self.env["ir.config_parameter"].sudo().get_param("buz_document_control.max_file_size_mb", 50))
                except ValueError:
                    max_mb = 50
                if len(base64.b64decode(record.original_file)) > max_mb * 1024 * 1024:
                    raise ValidationError(_("The uploaded file exceeds the configured maximum size."))

    @api.model_create_multi
    def create(self, vals_list):
        self._check_manager()
        records = super().create(vals_list)
        for record, vals in zip(records, vals_list):
            if vals.get("original_file"):
                record._generate_preview()
        return records

    def write(self, vals):
        protected = {"original_file", "original_filename", "revision", "effective_date", "change_description"}
        if protected.intersection(vals) and any(r.state == "published" for r in self):
            raise ValidationError(_("A published revision is immutable. Create a new revision instead."))
        if not self.env.su:
            self._check_manager()
        result = super().write(vals)
        if "original_file" in vals:
            for record in self:
                record._generate_preview()
        return result

    def unlink(self):
        if any(r.state == "published" for r in self) and not self.env.user.has_group("buz_document_control.group_document_admin"):
            raise ValidationError(_("Published revisions cannot be deleted. Mark them obsolete or archive the document."))
        self._check_manager()
        return super().unlink()

    def _check_manager(self):
        user = self.env.user
        if not (user.has_group("buz_document_control.group_document_manager") or user.has_group("buz_document_control.group_document_admin")):
            raise AccessError(_("Only Document Managers can change document revisions."))

    def action_send_review(self):
        self._check_manager()
        self.filtered(lambda r: r.state == "draft").write({"state": "review"})

    def action_cancel(self):
        self._check_manager()
        self.filtered(lambda r: r.state == "draft").write({"state": "cancelled"})

    def action_publish(self):
        self._check_manager()
        for record in self:
            if record.state not in ("draft", "review"):
                raise ValidationError(_("Only draft or review revisions can be published."))
            if not (record.original_file and record.revision and record.effective_date and record.change_description):
                raise ValidationError(_("Revision, original file, effective date and change description are required before publishing."))
            old = record.document_id.current_revision_id
            # One ORM transaction makes old/current/new state changes atomic.
            if old and old != record and old.state == "published":
                old.write({"state": "obsolete", "obsolete_by": self.env.user.id, "obsolete_date": fields.Datetime.now()})
            record.write({"state": "published", "published_by": self.env.user.id, "published_date": fields.Datetime.now()})
            record.document_id.write({"current_revision_id": record.id, "state": "published", "active": True})

    def action_mark_obsolete(self):
        self._check_manager()
        for record in self:
            if record.document_id.current_revision_id == record:
                raise ValidationError(_("Publish a replacement revision before obsoleting the current revision."))
            record.write({"state": "obsolete", "obsolete_by": self.env.user.id, "obsolete_date": fields.Datetime.now()})

    def action_regenerate_preview(self):
        self._check_manager()
        for record in self:
            record._generate_preview()

    def action_preview(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": "/buz_document/preview/%s" % self.id, "target": "new"}

    def action_download(self):
        self.ensure_one()
        return {"type": "ir.actions.act_url", "url": "/buz_document/download/%s" % self.id, "target": "self"}

    def _next_revision(self):
        self.ensure_one()
        if self.revision.isdigit():
            return str(int(self.revision) + 1).zfill(len(self.revision))
        return self.revision

    def _generate_preview(self):
        """Handle the cheap cases inline; hand the LibreOffice conversion off to cron.

        A synchronous soffice call (up to 120s) inside an HTTP request holds the
        request's DB transaction open for that whole time, which can exhaust the
        worker pool under load. Convertible files are only flagged "pending" here;
        _cron_generate_pending_previews() does the actual conversion outside any
        user-facing transaction.
        """
        self.ensure_one()
        if not self.original_file:
            return self.write({"preview_status": "none", "preview_file": False, "preview_filename": False, "preview_error": False})
        ext = os.path.splitext(self.original_filename or "")[1].lower()
        if ext == ".pdf":
            return self.write({"preview_file": self.original_file, "preview_filename": self.original_filename, "preview_status": "ready", "preview_error": False})
        if ext not in CONVERTIBLE_EXTENSIONS:
            return self.write({"preview_status": "failed", "preview_error": _("Preview is available only for PDF, Word, Excel and PowerPoint documents.")})
        return self.write({"preview_status": "pending", "preview_error": False})

    def _cron_generate_pending_previews(self, batch_size=20):
        """Run by ir_cron_generate_pending_previews. Converts queued revisions to PDF previews."""
        records = self.search([("preview_status", "=", "pending")], limit=batch_size)
        for record in records:
            record._run_preview_conversion()

    def _run_preview_conversion(self):
        self.ensure_one()
        ext = os.path.splitext(self.original_filename or "")[1].lower()
        if not self.original_file or ext not in CONVERTIBLE_EXTENSIONS:
            return self.write({"preview_status": "failed", "preview_error": _("Preview is available only for PDF, Word, Excel and PowerPoint documents.")})
        office = shutil.which("libreoffice") or shutil.which("soffice")
        if not office:
            return self.write({"preview_status": "failed", "preview_error": _("Document preview is unavailable because the document conversion service is not installed.")})
        safe_name = "source" + ext
        try:
            with tempfile.TemporaryDirectory(prefix="odoo_doc_preview_") as directory:
                source = os.path.join(directory, safe_name)
                with open(source, "wb") as stream:
                    stream.write(base64.b64decode(self.original_file))
                completed = subprocess.run([office, "--headless", "--convert-to", "pdf", "--outdir", directory, source], capture_output=True, timeout=120, check=False)
                target = os.path.join(directory, "source.pdf")
                if completed.returncode or not os.path.isfile(target):
                    raise RuntimeError("conversion did not produce a PDF")
                with open(target, "rb") as stream:
                    preview = base64.b64encode(stream.read())
            result = self.write({"preview_file": preview, "preview_filename": "%s.pdf" % os.path.splitext(self.original_filename or "document")[0], "preview_status": "ready", "preview_error": False})
            self.env.cr.commit()  # release the row lock promptly; cron processes remaining pending records independently
            return result
        except (OSError, ValueError, subprocess.TimeoutExpired, RuntimeError):
            self.write({"preview_status": "failed", "preview_error": _("The document could not be converted to a preview. The original file remains available for download.")})
            self.env.cr.commit()
            return False
