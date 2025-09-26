from odoo import api, fields, models, _
from odoo.exceptions import UserError


class HrExpense(models.Model):
    _inherit = 'hr.expense'

    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain=[('supplier_rank', '>', 0)],
        help='Vendor to pay directly instead of reimbursing employee'
    )

    @api.onchange('clear_mode')
    def _onchange_clear_mode(self):
        """Clear vendor_id if changing to Reimburse Employee mode"""
        if hasattr(self, 'clear_mode') and self.clear_mode == 'reimburse_employee':
            self.vendor_id = False


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    def _get_vendor_expense_lines(self):
        """Group expense lines by vendor_id for Pay Vendor mode"""
        vendor_groups = {}
        employee_lines = self.env['hr.expense']
        
        for expense in self.expense_line_ids:
            if expense.vendor_id:
                vendor_key = (expense.vendor_id.id, expense.company_id.id, expense.currency_id.id)
                if vendor_key not in vendor_groups:
                    vendor_groups[vendor_key] = self.env['hr.expense']
                vendor_groups[vendor_key] |= expense
            else:
                employee_lines |= expense
        
        return vendor_groups, employee_lines

    def _create_vendor_bills_for_vendors(self, vendor_groups):
        """Create separate vendor bills for each vendor in Pay Vendor mode"""
        bills = self.env['account.move']
        
        for (vendor_id, company_id, currency_id), expense_lines in vendor_groups.items():
            vendor = self.env['res.partner'].browse(vendor_id)
            
            # Group expenses by account and taxes to create proper invoice lines
            account_tax_groups = {}
            for expense in expense_lines:
                account = expense.account_id
                taxes = tuple(expense.tax_ids.ids)
                key = (account.id, taxes)
                
                if key not in account_tax_groups:
                    account_tax_groups[key] = {
                        'amount': 0,
                        'expenses': self.env['hr.expense'],
                        'tax_ids': expense.tax_ids.ids,
                        'analytic_account_id': expense.analytic_account_id.id,
                        'analytic_tag_ids': expense.analytic_tag_ids.ids
                    }
                
                account_tax_groups[key]['amount'] += expense.total_amount
                account_tax_groups[key]['expenses'] |= expense
            
            # Create vendor bill with grouped lines
            bill_vals = {
                'move_type': 'in_invoice',
                'partner_id': vendor.id,
                'invoice_date': fields.Date.context_today(self),
                'date': fields.Date.context_today(self),
                'currency_id': currency_id,
                'company_id': company_id,
                'ref': f'Expense Sheet {self.name} - Vendor {vendor.name}',
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
                    line_vals['quantity'] = single_expense.quantity
                    line_vals['price_unit'] = single_expense.unit_amount  # Use unit_amount to correctly handle taxes
                
                if group_data['analytic_account_id']:
                    line_vals['analytic_account_id'] = group_data['analytic_account_id']
                if group_data['analytic_tag_ids']:
                    line_vals['analytic_tag_ids'] = [(6, 0, group_data['analytic_tag_ids'])]
                
                bill_vals['invoice_line_ids'].append((0, 0, line_vals))
            
            bill = self.env['account.move'].create(bill_vals)
            bills |= bill
        
        return bills

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
                    'analytic_account_id': expense.analytic_account_id.id,
                    'analytic_tag_ids': expense.analytic_tag_ids.ids
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
                line_vals['quantity'] = single_expense.quantity
                line_vals['price_unit'] = single_expense.unit_amount  # Use unit_amount to correctly handle taxes
                
            if group_data['analytic_account_id']:
                line_vals['analytic_account_id'] = group_data['analytic_account_id']
            if group_data['analytic_tag_ids']:
                line_vals['analytic_tag_ids'] = [(6, 0, group_data['analytic_tag_ids'])]
            
            bill_vals['invoice_line_ids'].append((0, 0, line_vals))
        
        return self.env['account.move'].create(bill_vals)

    def action_approve_expense_sheets(self):
        """Override approval to create draft vendor bills based on clear mode"""
        res = super(HrExpenseSheet, self).action_approve_expense_sheets()
        
        for sheet in self:
            if sheet.state == 'approve':
                if sheet.clear_mode == 'pay_vendor':
                    # Create bills for vendors and for employee (if any)
                    vendor_groups, employee_lines = sheet._get_vendor_expense_lines()
                    
                    bills = self.env['account.move']
                    
                    # Create bills for vendors
                    if vendor_groups:
                        bills |= sheet._create_vendor_bills_for_vendors(vendor_groups)
                    
                    # Create bill for employee (for lines without vendor)
                    if employee_lines:
                        employee_bill = sheet._create_vendor_bill_for_employee(employee_lines)
                        bills |= employee_bill
                    
                    # Link bills to the expense sheet and create activities
                    for bill in bills:
                        sheet._create_activity_for_bill(bill)
                        
                elif sheet.use_advance and sheet.advance_box_id:
                    # Original behavior: create single bill for employee
                    sheet._create_vendor_bill_and_activity()
        
        return res

    def _create_activity_for_bill(self, bill):
        """Create activity for accounting team when bills are created"""
        activity_type_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_advance.advance_notify_activity_type_id', 0))
        user_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_advance.advance_notify_user_id', 0))
        group_id = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_advance.advance_notify_group_id', 0))
        deadline_days = int(self.env['ir.config_parameter'].sudo().get_param(
            'employee_advance.advance_notify_deadline_days', 1))
        
        activity_values = {
            'activity_type_id': activity_type_id,
            'summary': f'Vendor Bill {bill.name} requires review from expense sheet {self.name}',
            'date_deadline': fields.Date.add(fields.Date.context_today(self), days=deadline_days),
            'automated': True,
        }
        
        if user_id:
            activity_values['user_id'] = user_id
        elif group_id and bill.partner_id.user_id:
            # Assign to the partner's related user if available
            activity_values['user_id'] = bill.partner_id.user_id.id
        else:
            # Default to current user if no specific user or group is set
            activity_values['user_id'] = self.env.user.id
        
        bill.activity_schedule(
            activity_type_id=activity_values['activity_type_id'],
            summary=activity_values['summary'],
            note=f"Vendor bill {bill.name} created from expense sheet {self.name}. Please review and post.",
            user_id=activity_values['user_id'],
            date_deadline=activity_values['date_deadline']
        )