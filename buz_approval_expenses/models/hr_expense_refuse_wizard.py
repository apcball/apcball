from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrExpenseRefuseWizard(models.TransientModel):
    _name = 'hr.expense.refuse.wizard'
    _description = 'Wizard for refusing an Expense Report with reason'

    expense_sheet_id = fields.Many2one(
        'hr.expense.sheet',
        string='Expense Report',
        required=True,
        default=lambda self: self.env.context.get('default_expense_sheet_id')
    )
    refuse_reason = fields.Text(
        string='Refusal Reason',
        required=True
    )

    def action_confirm_refuse(self):
        self.ensure_one()
        if not self.expense_sheet_id:
            raise UserError(_("No expense report selected."))

        if self.expense_sheet_id.state not in ('wait_manager', 'wait_acc_manager'):
            raise UserError(_("Expense Report cannot be refused in its current state."))

        self.expense_sheet_id.write({
            'state': 'refused',
            'refuse_reason': self.refuse_reason,
        })
        self.expense_sheet_id.expense_line_ids.write({'state': 'refused'})

        # ส่งการแจ้งเตือน
        self.expense_sheet_id.message_post(
            body=_('Expense report refused. Reason: %s') % self.refuse_reason,
            message_type='notification'
        )

        return {'type': 'ir.actions.act_window_close'}