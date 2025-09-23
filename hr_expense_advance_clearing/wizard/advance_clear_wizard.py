
from odoo import models, fields, _
from odoo.exceptions import UserError

class AdvanceClearWizard(models.TransientModel):
    _name = "advance.clear.wizard"
    _description = "Clear Expense from Advance (manual)"

    expense_sheet_id = fields.Many2one("hr.expense.sheet", required=True)
    amount = fields.Monetary(required=True, help="Amount to clear from advance")
    currency_id = fields.Many2one("res.currency", default=lambda self: self.env.company.currency_id)

    def action_clear(self):
        self.ensure_one()
        sheet = self.expense_sheet_id
        if not sheet.advance_box_id or not sheet.advance_box_id.account_id:
            raise UserError(_("Please set Advance Box on the expense sheet."))
        # This wizard is optional: create an adjusting move if needed
        # Typically not used if action_sheet_move_create already redirected the credit line.
        return {"type": "ir.actions.act_window_close"}
