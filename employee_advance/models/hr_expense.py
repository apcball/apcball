from odoo import api, fields, models, _

from odoo.exceptions import UserError

class HrExpense(models.Model):
    _inherit = 'hr.expense'

    # expense_vendor_id = fields.Many2one(
    #     'res.partner',
    #     string='Vendor',
    #     domain="[('supplier_rank', '>', 0), ('is_company', '=', True)]",
    #     help="Vendor for this expense line. Required when using pay_vendor or mixed clear mode."
    # )

    def _validate_vendor_requirements(self):
        """Validate vendor requirements based on clear_mode"""
        # Temporarily disabled vendor validation
        pass

    def write(self, vals):
        """Override write to validate vendor requirements"""
        result = super(HrExpense, self).write(vals)
        # Temporarily disabled vendor validation
        return result


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    def _create_vendor_bill_for_employee(self, employee_lines):
        """Create vendor bill for employee reimbursement (existing functionality)"""
        if not employee_lines:
            return self.env['account.move']
        
        # Check if employee has private address
        employee = self.employee_id
        partner_id = False
        
        # Method 1: Check if address_home_id exists (from hr_contract module)
        if hasattr(employee, 'address_home_id'):
            partner_id = employee.sudo().address_home_id.id if employee.sudo().address_home_id else False
        
        # If still not found, try to get the related user's partner (which might contain private address)
        if not partner_id and employee.user_id:
            partner_id = employee.user_id.partner_id.id
        
        # If still not found, default to employee's address_id (work address)
        if not partner_id:
            partner_id = employee.address_id.id if employee.address_id else False
        
        if not partner_id:
            raise UserError(_(
                "Employee %s does not have a private address. Please set the employee's home address."
            ) % employee.name)
        
        # Group expenses by account and taxes to create proper invoice lines
        account_tax_groups = {}
        for expense in employee_lines:
            account = expense.account_id
            taxes = tuple(expense.tax_ids.ids)
            key = (account.id, taxes)
            
            if key not in account_tax_groups:
                account_tax_groups[key] = {
                    'amount': 0,
                    'expenses': self.env['hr.expense'],
                    'tax_ids': expense.tax_ids.ids,
                    'analytic_account_id': expense.account_analytic_id.id if hasattr(expense, 'account_analytic_id') and expense.account_analytic_id else False,
                    'analytic_tag_ids': expense.analytic_tag_ids.ids if hasattr(expense, 'analytic_tag_ids') else []
                }
            
            account_tax_groups[key]['amount'] += expense.total_amount
            account_tax_groups[key]['expenses'] |= expense
        
        # Create vendor bill with grouped lines
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner_id,
            'invoice_date': fields.Date.context_today(self),
            'date': fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'ref': f'Expense Sheet {self.name}',
            'expense_sheet_id': self.id,
            'invoice_line_ids': []
        }
        
        for (account_id, taxes_tuple), group_data in account_tax_groups.items():
            line_vals = {
                'name': ', '.join(group_data['expenses'].mapped('name')),
                'quantity': 1,
                'price_unit': group_data['amount'],
                'account_id': account_id,
                'tax_ids': [(6, 0, list(set(group_data['tax_ids'])))],
            }
            
            # Properly handle taxes and amounts
            expense_lines = group_data['expenses']
            # If multiple expenses with taxes, calculate properly
            if len(expense_lines) > 1:
                # Combine amounts from all expenses in this group
                line_vals['name'] = ', '.join(expense_lines.mapped('name'))
            else:
                # Use the single expense details
                single_expense = expense_lines[0]
                line_vals['name'] = single_expense.name
                line_vals['quantity'] = single_expense.quantity if hasattr(single_expense, 'quantity') else 1
                line_vals['price_unit'] = single_expense.unit_amount if hasattr(single_expense, 'unit_amount') and single_expense.unit_amount else single_expense.price_unit  # Use appropriate field to correctly handle taxes
                
            if group_data.get('analytic_account_id'):
                line_vals['analytic_account_id'] = group_data['analytic_account_id']
            if group_data.get('analytic_tag_ids', []):
                line_vals['analytic_tag_ids'] = [(6, 0, group_data['analytic_tag_ids'])]
            
            bill_vals['invoice_line_ids'].append((0, 0, line_vals))
        
        return self.env['account.move'].create(bill_vals)

    def action_approve_expense_sheets(self):
        """Override approval to create draft vendor bills based on clear mode"""
        res = super(HrExpenseSheet, self).action_approve_expense_sheets()
        
        for sheet in self:
            if sheet.state == 'approve':
                if sheet.use_advance and sheet.advance_box_id:
                    # Original behavior: create single bill for employee
                    sheet._create_vendor_bill_and_activity()
        
        return res