from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    approver_id = fields.Many2one(
        "res.users",
        string="Manager Approver",
    )
    approval_date = fields.Datetime(
        string="Approval Date",
        copy=False,
    )
    approval_signature = fields.Binary(
        string="Signature",
        copy=False,
        attachment=True,
    )