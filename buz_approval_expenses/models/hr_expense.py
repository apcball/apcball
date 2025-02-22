from odoo import models, fields, api, _
from odoo.exceptions import UserError

class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    state = fields.Selection(
        selection_add=[
            ('wait_manager', 'Waiting Manager Approval'),
            ('wait_acc_manager', 'Waiting ACC Manager Approval'),
            ('refused', 'Refused'),
        ],
        ondelete={
            'wait_manager': 'cascade',
            'wait_acc_manager': 'cascade',
            'refused': 'cascade'
        }
    )

    refuse_reason = fields.Text(string="Refusal Reason")

    def action_submit_sheet(self):
        res = super(HrExpenseSheet, self).action_submit_sheet()
        self.write({'state': 'wait_manager'})
        activity_type_id = self.env.ref('mail.mail_activity_data_todo').id
        manager_user = self.employee_id.parent_id.user_id
        if manager_user:
            self.env['mail.activity'].with_context(mail_notify_noemail=True).create({
                'activity_type_id': activity_type_id,
                'note': _('New expense report submitted for approval'),
                'res_id': self.id,
                'res_model_id': self.env.ref('hr_expense.model_hr_expense_sheet').id,
                'user_id': manager_user.id,
                'summary': _('Expense Approval'),
            })
        return res

    def action_approve_manager(self):
        self.ensure_one()
        self.write({'state': 'wait_acc_manager'})
        acc_manager_id = int(
            self.env['ir.config_parameter']
            .sudo()
            .get_param('buz_approval_expenses.expense_acc_manager_id', 0)
        )
        if acc_manager_id:
            activity_type_id = self.env.ref('mail.mail_activity_data_todo').id
            self.env['mail.activity'].with_context(mail_notify_noemail=True).create({
                'activity_type_id': activity_type_id,
                'note': _('Expense report waiting for ACC manager approval'),
                'res_id': self.id,
                'res_model_id': self.env.ref('hr_expense.model_hr_expense_sheet').id,
                'user_id': acc_manager_id,
                'summary': _('Expense Final Approval'),
            })
        return True

    def action_approve_acc_manager(self):
        self.ensure_one()
        self.write({
            'state': 'approve',
            'user_id': self.env.user.id,
        })
        self.expense_line_ids.write({'state': 'approved'})
        return True

    def action_refuse_sheet(self):
        self.ensure_one()
        return {
            'name': _('Refuse Expense Report'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'hr.expense.refuse.wizard',
            'view_id': self.env.ref('buz_approval_expenses.hr_expense_refuse_wizard_form_view').id,
            'target': 'new',
            'context': {'default_expense_sheet_id': self.id},
        }

    def action_reset_to_draft(self):
        self.ensure_one()
        self.write({
            'state': 'draft',
            'refuse_reason': False,
        })
        self.expense_line_ids.write({'state': 'draft'})
        return True