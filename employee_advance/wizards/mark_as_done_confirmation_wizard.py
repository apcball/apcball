from odoo import api, fields, models
from odoo.exceptions import UserError


class MarkAsDoneConfirmationWizard(models.TransientModel):
    _name = 'mark.as.done.confirmation.wizard'
    _description = 'Mark as Done Confirmation Wizard'

    expense_sheet_id = fields.Many2one('hr.expense.sheet', string='Expense Sheet', required=True)
    employee_id = fields.Many2one('hr.employee', string='Employee', readonly=True)
    total_amount = fields.Monetary(string='Total Amount', readonly=True, currency_field='currency_id')
    bills_count = fields.Integer(string='Bills Count', readonly=True)
    advance_cleared = fields.Boolean(string='Advance Cleared', readonly=True)
    expense_line_ids = fields.One2many('hr.expense', related='expense_sheet_id.expense_line_ids', string='Expense Lines', readonly=True)
    currency_id = fields.Many2one('res.currency', related='expense_sheet_id.currency_id', string='Currency', readonly=True)

    @api.model
    def default_get(self, fields_list):
        """Set default values from the expense sheet"""
        res = super().default_get(fields_list)
        
        if self.env.context.get('active_model') == 'hr.expense.sheet' and self.env.context.get('active_id'):
            expense_sheet = self.env['hr.expense.sheet'].browse(self.env.context['active_id'])
            if expense_sheet.exists():
                res['expense_sheet_id'] = expense_sheet.id
                res['employee_id'] = expense_sheet.employee_id.id
                res['total_amount'] = expense_sheet.total_amount
                res['bills_count'] = len(expense_sheet.account_move_ids.filtered(lambda m: m.move_type == 'in_invoice'))
                
                # Check if advance has been cleared - check for related advance clearing journal entries
                advance_cleared = False
                if expense_sheet.account_move_ids:
                    # Look for journal entries that have advance clearing indicators
                    for move in expense_sheet.account_move_ids:
                        if hasattr(move, 'is_advance_clearing') and move.is_advance_clearing:
                            advance_cleared = True
                            break
                        # Also check if there are payable entries that might indicate advance clearing
                        elif any(line.account_id.account_type == 'liability_payable' and line.debit > 0 for line in move.line_ids):
                            advance_cleared = True
                
                res['advance_cleared'] = advance_cleared

        elif self.env.context.get('default_expense_sheet_id'):
            expense_sheet_id = self.env.context.get('default_expense_sheet_id')
            expense_sheet = self.env['hr.expense.sheet'].browse(expense_sheet_id)
            if expense_sheet.exists():
                res['expense_sheet_id'] = expense_sheet.id
                res['employee_id'] = expense_sheet.employee_id.id
                res['total_amount'] = expense_sheet.total_amount
                res['bills_count'] = len(expense_sheet.account_move_ids.filtered(lambda m: m.move_type == 'in_invoice'))
                
                # Check if advance has been cleared
                advance_cleared = False
                if expense_sheet.account_move_ids:
                    for move in expense_sheet.account_move_ids:
                        if hasattr(move, 'is_advance_clearing') and move.is_advance_clearing:
                            advance_cleared = True
                            break
                        elif any(line.account_id.account_type == 'liability_payable' and line.debit > 0 for line in move.line_ids):
                            advance_cleared = True
                
                res['advance_cleared'] = advance_cleared

        return res
    
    def action_confirm_mark_as_done(self):
        """Confirm and mark the expense sheet as done"""
        if self.expense_sheet_id:
            # Perform additional validation
            if self.expense_sheet_id.state in ['done', 'cancel']:
                raise UserError("This expense sheet is already marked as done or cancelled.")
            
            # Check if all required processes have been completed
            if self.expense_sheet_id.total_amount > 0:
                # Verify bills have been created if amount > 0
                active_bills = self.expense_sheet_id.account_move_ids.filtered(
                    lambda m: m.move_type == 'in_invoice' and m.state == 'posted'
                )
                
                if not active_bills:
                    # Show a warning but allow user to proceed since they confirmed
                    pass  # Allow proceeding even without bills since this is a confirmation step
            
            # Call the actual method to mark as done
            return self.expense_sheet_id.action_mark_as_done_without_confirmation()
        
        return {'type': 'ir.actions.act_window_close'}