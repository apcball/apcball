from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    _RETENTION_ALLOWED_ACCOUNT_TYPES = ("asset_receivable", "asset_current")

    sale_retention_account_id = fields.Many2one(
        "account.account",
        string="Default Retention Receivable Account",
        domain="[('account_type', 'in', ('asset_receivable', 'asset_current'))]",
        config_parameter="sale_retention_receivable.default_account_id",
        help="Default account used for retention receivable entries.",
    )
    sale_retention_default_percent = fields.Float(
        string="Default Retention Percentage (%)",
        config_parameter="sale_retention_receivable.default_percent",
        help="Default retention percentage applied on sale orders.",
    )
    sale_retention_default_days = fields.Integer(
        string="Default Retention Days",
        config_parameter="sale_retention_receivable.default_days",
        help="Default number of days after invoice date for retention due date.",
    )

    @api.constrains("sale_retention_account_id")
    def _check_sale_retention_account_id(self):
        for settings in self:
            account = settings.sale_retention_account_id
            if account and account.account_type not in self._RETENTION_ALLOWED_ACCOUNT_TYPES:
                raise ValidationError(
                    _(
                        "Default Retention Receivable Account must be a Receivable "
                        "or Current Asset account."
                    )
                )
