from odoo import fields, models


class BuzDocumentDownloadLog(models.Model):
    _name = "buz.document.download.log"
    _description = "Document Download Audit Log"
    _order = "download_date desc"

    document_id = fields.Many2one("buz.document", required=True, ondelete="cascade", index=True)
    revision_id = fields.Many2one("buz.document.revision", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one("res.users", required=True, ondelete="restrict", index=True)
    download_date = fields.Datetime(required=True, default=fields.Datetime.now, index=True)
    action_type = fields.Selection([( "preview", "Preview"), ("download", "Download")], required=True)
