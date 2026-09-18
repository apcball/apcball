from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    hide_unlock_cancel_buttons = fields.Boolean(
        compute="_compute_hide_unlock_cancel_buttons",
        help="Technical field for hiding Unlock and Cancel buttons for selected users.",
    )

    approver_id = fields.Many2one(
        "res.users",
        string="Manager Approver",
    )
    approval_date = fields.Date(
        string="Approval Date",
        copy=False,
    )
    approval_signature = fields.Binary(
        related="approver_id.employee_id.signature_image",
        string="Signature",
        readonly=True,
    )

    @api.depends("delivery_count")
    @api.depends_context("uid")
    def _compute_hide_unlock_cancel_buttons(self):
        user_can_hide_buttons = self.env.user.has_group(
            "buz_customize_sale.group_hide_so_unlock"
        )
        for order in self:
            order.hide_unlock_cancel_buttons = bool(
                user_can_hide_buttons and order.delivery_count
            )
