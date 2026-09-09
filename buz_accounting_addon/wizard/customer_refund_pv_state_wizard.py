from odoo import fields, models, _
from odoo.exceptions import UserError


class BuzCustomerRefundPvStateWizard(models.TransientModel):
    _name = "buz.customer.refund.pv.state.wizard"
    _description = "Customer Refund PV State Change Reason"

    pv_id = fields.Many2one(
        "buz.customer.refund.pv",
        string="Customer Refund PV",
        required=True,
        readonly=True,
        ondelete="cascade",
    )
    operation = fields.Selection([
        ("reset", "Reset to Draft"),
        ("cancel", "Cancel"),
    ], required=True, readonly=True)
    reason = fields.Text(string="Reason", required=True)

    def action_confirm(self):
        self.ensure_one()
        if not (
            self.env.user.has_group("account.group_account_invoice")
            or self.env.user.has_group("account.group_account_manager")
        ):
            raise UserError(_("Only Accounting Users or Accounting Managers can perform this action."))
        reason = (self.reason or "").strip()
        if not reason:
            raise UserError(_("Please enter a reason."))
        if not self.pv_id:
            raise UserError(_("Customer Refund PV is not available."))
        if self.operation == "reset":
            self.pv_id._reset_to_draft_with_reason(reason)
        else:
            self.pv_id._cancel_with_reason(reason)
        return {"type": "ir.actions.act_window_close"}
