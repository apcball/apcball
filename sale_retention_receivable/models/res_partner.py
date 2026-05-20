from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    sale_retention_enabled = fields.Boolean(
        string="Enable Sales Retention",
        help="Apply retention on invoices for this customer.",
    )
    sale_retention_percent = fields.Float(
        string="Retention Percentage (%)",
        help="Default retention percentage for this customer.",
    )
    sale_retention_days = fields.Integer(
        string="Retention Days",
        help="Default number of days after invoice date for retention due date.",
    )