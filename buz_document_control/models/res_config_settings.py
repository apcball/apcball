from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    document_review_warning_days = fields.Integer(
        string="Review warning days", config_parameter="buz_document_control.review_warning_days", default=30)
    document_max_file_size_mb = fields.Integer(
        string="Maximum document file size (MB)", config_parameter="buz_document_control.max_file_size_mb", default=50)
    document_enable_download_log = fields.Boolean(
        string="Enable preview/download audit log", config_parameter="buz_document_control.enable_download_log")
