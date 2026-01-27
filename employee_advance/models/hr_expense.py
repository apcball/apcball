from odoo import api, fields, models, _

from odoo.exceptions import UserError

class HrExpense(models.Model):
    _inherit = 'hr.expense'

    expense_vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        domain="[('supplier_rank', '>', 0)]",
        help="Vendor for this expense line. If specified, bill will be created for this vendor. If not specified, bill will be created for employee."
    )

    wht_tax_id = fields.Many2one(
        comodel_name="account.withholding.tax",
        string="WHT",
        compute="_compute_wht_tax_id",
        store=True,
        readonly=False,
        tracking=True,
    )

    @api.depends("product_id")
    def _compute_wht_tax_id(self):
        for rec in self:
            rec.wht_tax_id = rec.product_id.supplier_wht_tax_id or False

    def _validate_vendor_requirements(self):
        """Validate vendor requirements based on clear_mode"""
        # No specific validation needed - vendor is optional
        pass

    def write(self, vals):
        """Override write to validate vendor requirements"""
        result = super(HrExpense, self).write(vals)
        # Call validation if needed
        self._validate_vendor_requirements()
        return result


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    def _calculate_expense_base_amount(self, expense):
        """Calculate expense amount before tax for included tax expenses"""
        if not expense.tax_ids:
            return expense.price_unit
        
        # For included tax, calculate the base amount (excluding tax)
        # price_unit = base_amount * (1 + tax_rate)
        # base_amount = price_unit / (1 + tax_rate)
        
        total_tax_rate = 0
        for tax in expense.tax_ids:
            if tax.amount_type == 'percent':
                total_tax_rate += tax.amount / 100
        
        if total_tax_rate > 0:
            base_amount = expense.price_unit / (1 + total_tax_rate)
        else:
            base_amount = expense.price_unit
            
        return base_amount

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
        
        # Group expenses by account, taxes, analytic account, analytic tags, product, and WHT tax to create proper invoice lines
        account_tax_groups = {}
        for expense in employee_lines:
            account = expense.account_id
            taxes = tuple(expense.tax_ids.ids)
            analytic_distribution = expense.analytic_distribution or {}
            wht_tax = expense.wht_tax_id.id if hasattr(expense, 'wht_tax_id') and expense.wht_tax_id else False
            product_id = expense.product_id.id if expense.product_id else False
            # Include product_id in key to separate lines for different products
            key = (account.id, taxes, tuple(sorted(analytic_distribution.keys())), wht_tax, product_id)
            
            if key not in account_tax_groups:
                account_tax_groups[key] = {
                    'amount': 0,
                    'expenses': self.env['hr.expense'],
                    'tax_ids': expense.tax_ids.ids,
                    'analytic_distribution': analytic_distribution,
                    'wht_tax_id': wht_tax,
                    'product_id': product_id
                }
            
            # Use price_unit (before tax) to avoid VAT duplication when tax_ids are applied
            # Calculate base amount for included tax expenses to avoid VAT duplication
            base_amount = self._calculate_expense_base_amount(expense)
            account_tax_groups[key]['amount'] += base_amount
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
        
        for (account_id, taxes_tuple, analytic_keys, wht_tax, product_id), group_data in account_tax_groups.items():
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
                # Calculate base amount for included tax expenses to avoid VAT duplication
                line_vals['price_unit'] = self._calculate_expense_base_amount(single_expense)
                
            if group_data['analytic_distribution']:
                line_vals['analytic_distribution'] = group_data['analytic_distribution']
            if group_data.get('product_id'):
                line_vals['product_id'] = group_data['product_id']
            if group_data.get('wht_tax_id'):
                line_vals['wht_tax_id'] = group_data['wht_tax_id']
            
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