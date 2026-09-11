import base64
import mimetypes
import re
from urllib.parse import quote

from odoo import http
from odoo.http import request
from werkzeug.exceptions import Forbidden, NotFound


class BuzDocumentController(http.Controller):
    def _revision_or_404(self, revision_id, preview=False):
        revision = request.env["buz.document.revision"].browse(revision_id).exists()
        if not revision:
            raise NotFound()
        # Do not sudo before access rights/rules are evaluated: this prevents guessed URLs.
        try:
            revision.check_access_rights("read")
            revision.check_access_rule("read")
            revision.document_id.check_access_rights("read")
            revision.document_id.check_access_rule("read")
        except Exception as error:
            raise Forbidden() from error
        if not request.env.user.has_group("buz_document_control.group_document_manager") and revision.state != "published":
            raise Forbidden()
        if preview and not (revision.preview_file and revision.preview_status == "ready"):
            raise NotFound()
        if not preview and not revision.original_file:
            raise NotFound()
        return revision

    @staticmethod
    def _filename(value, fallback):
        # Browser header-safe; filenames never become filesystem paths.
        clean = re.sub(r"[\r\n\\/\x00]", "_", value or fallback)
        return clean[:180]

    @staticmethod
    def _content_disposition(filename, inline=False):
        # Built directly (not via odoo.http.content_disposition + string replace)
        # so it doesn't depend on that helper's internal "attachment; ..." format.
        disposition = "inline" if inline else "attachment"
        return "%s; filename*=UTF-8''%s" % (disposition, quote(filename))

    def _log(self, revision, action):
        enabled = request.env["ir.config_parameter"].sudo().get_param("buz_document_control.enable_download_log", "False")
        if enabled.lower() in ("1", "true", "yes"):
            request.env["buz.document.download.log"].sudo().create({"document_id": revision.document_id.id, "revision_id": revision.id, "user_id": request.env.user.id, "action_type": action})

    @http.route("/buz_document/preview/<int:revision_id>", type="http", auth="user", methods=["GET"])
    def preview(self, revision_id, **kwargs):
        revision = self._revision_or_404(revision_id, preview=True)
        self._log(revision, "preview")
        return request.make_response(base64.b64decode(revision.preview_file), headers=[
            ("Content-Type", "application/pdf"),
            ("Content-Disposition", self._content_disposition(self._filename(revision.preview_filename, "preview.pdf"), inline=True)),
            ("X-Content-Type-Options", "nosniff"),
        ])

    @http.route("/buz_document/download/<int:revision_id>", type="http", auth="user", methods=["GET"])
    def download(self, revision_id, **kwargs):
        revision = self._revision_or_404(revision_id)
        self._log(revision, "download")
        filename = self._filename(revision.original_filename, "document")
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return request.make_response(base64.b64decode(revision.original_file), headers=[
            ("Content-Type", mime_type),
            ("Content-Disposition", self._content_disposition(filename)),
            ("X-Content-Type-Options", "nosniff"),
        ])
