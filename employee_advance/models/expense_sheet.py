from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    clear_mode = fields.Selection([
        ('reimburse_employee', 'Reimburse Employee'),
        ('pay_vendor', 'Pay to Vendor'),
        ('mixed', 'Mixed')
    ], string='Clear Mode', default='reimburse_employee', compute='_compute_clear_mode', store=True,
       help="Reimburse Employee: Create bills for employee's private address. "
            "Pay to Vendor: Create bills for vendors on each expense line. "
            "Mixed: Both employee and vendor bills will be created.")
    
    @api.depends("expense_line_ids", "is_auto_mode")
    def _compute_clear_mode(self):
        for sheet in self:
            if sheet.is_auto_mode:
                # AUTO mode - automatically determine clear mode
                has_vendor = any(exp.expense_vendor_id for exp in sheet.expense_line_ids)
                has_no_vendor = any(not exp.expense_vendor_id for exp in sheet.expense_line_ids)
                
                if has_vendor and has_no_vendor:
                    sheet.clear_mode = 'mixed'
                elif has_vendor:
                    sheet.clear_mode = 'pay_vendor'
                else:
                    sheet.clear_mode = 'reimburse_employee'
            else:
                # Manual mode - keep current value or default
                if not sheet.clear_mode:
                    sheet.clear_mode = 'reimburse_employee'
    
    bill_ids = fields.Many2many(
        'account.move',
        string='Vendor Bills',
        relation='hr_expense_sheet_account_move_rel',
        column1='expense_sheet_id',
        column2='move_id',
        readonly=True,
        copy=False
    )
    
    is_billed = fields.Boolean(
        string='Bills Created',
        default=False,
        readonly=True,
        help="Indicates if bills have been created for this expense sheet."
    )

    use_advance = fields.Boolean(
        string='Clear from Advance',
        default=True
    )
    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        domain="[('company_id', '=', company_id)]"
    )
    
    # AUTO mode fields
    is_auto_mode = fields.Boolean(
        string="Auto Mode",
        compute="_compute_auto_mode",
        help="Indicates if this sheet will use AUTO mode (automatic vendor bill separation)"
    )
    
    vendor_summary = fields.Text(
        string="Vendor Summary", 
        compute="_compute_vendor_summary",
        help="Summary of vendors and processing mode"
    )
    
    @api.depends("expense_line_ids")
    def _compute_auto_mode(self):
        for sheet in self:
            # Check if there are mixed vendors - use AUTO mode when multiple vendors exist
            unique_vendors = set(exp.expense_vendor_id.id if exp.expense_vendor_id else None for exp in sheet.expense_line_ids)
            sheet.is_auto_mode = len(unique_vendors) > 1
    
    @api.depends("expense_line_ids", "is_auto_mode")  
    def _compute_vendor_summary(self):
        for sheet in self:
            if sheet.is_auto_mode:
                # Show vendor summary in AUTO mode
                vendors_with_employee = []
                vendors_without_employee = []
                
                for exp in sheet.expense_line_ids:
                    if exp.expense_vendor_id:
                        vendor_name = exp.expense_vendor_id.name
                        if vendor_name not in vendors_with_employee:
                            vendors_with_employee.append(vendor_name)
                    else:
                        if sheet.employee_id.name not in vendors_without_employee:
                            vendors_without_employee.append(sheet.employee_id.name)
                
                summary_parts = []
                if vendors_with_employee:
                    summary_parts.append(f"Vendors: {', '.join(vendors_with_employee)}")
                if vendors_without_employee:
                    summary_parts.append(f"Employee: {', '.join(vendors_without_employee)}")
                    
                sheet.vendor_summary = f"🤖 AUTO MODE - แยกบิลตาม: {' | '.join(summary_parts)}"
            else:
                sheet.vendor_summary = ""
    bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        copy=False
    )
    payment_ids = fields.Many2many(
        'account.payment',
        string='Payments',
        compute='_compute_payment_ids'
    )
    can_clear_advance_wht = fields.Boolean(
        string='Can Clear Advance WHT',
        compute='_compute_can_clear_advance_wht'
    )

    @api.depends('bill_id')
    def _compute_payment_ids(self):
        for sheet in self:
            if sheet.bill_id:
                # Find payments that are reconciled with the bill
                reconciled_payments = self.env['account.payment']
                for line in sheet.bill_id.line_ids:
                    if line.account_id.account_type == 'liability_payable':
                        for partial_line in line.matched_debit_ids + line.matched_credit_ids:
                            payment = partial_line.debit_move_id.move_id or partial_line.credit_move_id.move_id
                            if payment._name == 'account.payment':
                                reconciled_payments |= payment
                sheet.payment_ids = reconciled_payments
            else:
                sheet.payment_ids = [(5, 0, 0)]  # Empty

    @api.depends('use_advance', 'advance_box_id', 'state', 'is_billed')
    def _compute_can_clear_advance_wht(self):
        """Check if WHT advance clearing is available"""
        for sheet in self:
            sheet.can_clear_advance_wht = (
                sheet.use_advance and 
                sheet.advance_box_id and 
                sheet.state == 'approve' and
                not sheet.is_billed
            )

    @api.onchange('use_advance')
    def _onchange_use_advance(self):
        """Clear advance box if not using advance"""
        if not self.use_advance:
            self.advance_box_id = False

    def action_approve_expense_sheets(self):
        """Override approval to create draft vendor bills - enhanced with vendor grouping"""
        res = super(HrExpenseSheet, self).action_approve_expense_sheets()
        
        for sheet in self:
            if sheet.state == 'approve':
                # Always use the enhanced vendor bill creation logic
                sheet.action_create_vendor_bills()
        
        return res

    def _create_vendor_bill_and_activity(self):
        """Create vendor bill and activity for accounting team"""
        self.ensure_one()
        
        # Check if employee has private address
        employee = self.employee_id
        # Check if employee has private address using the same logic as advance box
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
        
        # Check if advance account is set
        advance_box = self.advance_box_id
        if not advance_box.account_id:
            raise UserError(_("Please set the advance account for the selected advance box."))
        
        # Create vendor bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner_id,
            'invoice_date': fields.Date.context_today(self),
            'date': fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'ref': f'Expense Sheet {self.name}',
            'invoice_line_ids': [],
        }
        
        # Add expense lines to the bill
        for expense in self.expense_line_ids:
            bill_line_vals = {
                'name': expense.name,
                'quantity': expense.quantity,
                'price_unit': expense.price_unit,
                'tax_ids': [(6, 0, expense.tax_ids.ids)],
                'account_id': expense.account_id.id,
            }
            bill_vals['invoice_line_ids'].append((0, 0, bill_line_vals))
        
        bill = self.env['account.move'].create(bill_vals)
        
        # Link bill to expense sheet and also set advance box reference on the bill
        self.bill_id = bill.id
        # Also link the advance box to the bill for easier tracking
        bill.sudo().write({
            'advance_box_id': self.advance_box_id.id,
            'expense_sheet_id': self.id,
            'is_expense_advance_bill': True
        })
        
        # Add activity for accounting as per settings
        ICP = self.env['ir.config_parameter'].sudo()
        user_id = int(ICP.get_param('employee_advance.advance_notify_user_id', 0))
        group_id = int(ICP.get_param('employee_advance.advance_notify_group_id', 0))
        activity_type_id = int(ICP.get_param('employee_advance.advance_notify_activity_type_id', 0))
        deadline_days = int(ICP.get_param('employee_advance.advance_notify_deadline_days', 1))
        
        activity_vals = {
            'res_id': bill.id,
            'res_model_id': self.env['ir.model']._get_id('account.move'),
            'activity_type_id': activity_type_id or self.env.ref('employee_advance.mail_activity_type_advance_bill_review').id,
            'summary': f'Review vendor bill for expense sheet {self.name}',
            'user_id': user_id or self.env.ref('base.user_admin').id,
            'date_deadline': fields.Date.add(fields.Date.context_today(self), days=deadline_days),
        }
        
        if group_id:
            activity_vals['user_id'] = self.env['res.users'].search([('groups_id', '=', group_id)], limit=1).id or activity_vals['user_id']
        
        bill.activity_schedule(
            activity_type_id=activity_vals['activity_type_id'],
            summary=activity_vals['summary'],
            note=f"Expense sheet {self.name} has been approved. Please review the vendor bill.",
            user_id=activity_vals['user_id'],
            date_deadline=activity_vals['date_deadline']
        )
        
        # Log in chatter
        bill.message_post(body=_("Vendor bill created from expense sheet approval."))
        
        return bill

    def action_clear_advance(self):
        """Create Journal Entry to clear advance instead of opening Register Payment wizard"""
        self.ensure_one()
        
        if not self.bill_id:
            raise UserError(_("No vendor bill found for this expense sheet."))
        
        if self.bill_id.state != 'posted':
            raise UserError(_("The vendor bill must be posted before clearing the advance."))
        
        if self.bill_id.amount_residual <= 0:
            raise UserError(_("The vendor bill is already fully paid."))
        
        advance_box = self.advance_box_id
        if not advance_box:
            raise UserError(_("No advance box selected."))
        
        if not advance_box.account_id:
            raise UserError(_("The advance box does not have an account configured. Please set an account for the advance box."))
        
        # Call the existing method from account.move to handle JE creation
        return self.bill_id._clear_advance_using_advance_box(advance_box)

    def action_create_vendor_bills(self):
        """Create vendor bills based on vendor field - group by vendor and create separate bills"""
        self.ensure_one()
        
        # Run validations
        self._validate_fiscal_period()
        self._validate_expense_lines_for_clear_mode()
        
        if self.is_billed:
            raise UserError(_("Bills have already been created for this expense sheet."))
        
        # Check if any expenses have vendors - if so, use new grouping logic
        has_vendors = any(exp.expense_vendor_id for exp in self.expense_line_ids)
        
        if not has_vendors and (not self.clear_mode or self.clear_mode == 'reimburse_employee'):
            # For pure reimburse_employee mode without vendors, use the existing functionality
            if self.use_advance and self.advance_box_id:
                self._create_vendor_bill_and_activity()
                self.is_billed = True
            return
        
        # Create bills based on vendor grouping (new enhanced logic)
        bills = self._create_bills_by_vendor_grouping()
        
        if bills:
            self.bill_ids = [(4, bill.id) for bill in bills]
            self.is_billed = True
            
            # Post accounting activity to reviewers
            self._post_accounting_activity_for_bills(bills)
            
            # Log in chatter
            bill_names = ', '.join(bills.mapped('name'))
            self.message_post(body=_(f"Vendor bills created: {bill_names}"))
            
        return bills

    def _create_bills_by_vendor_grouping(self):
        """Enhanced: Group expenses by vendor and create separate bills per vendor.
        If no vendor specified, group under employee name."""
        bills = self.env['account.move']
        
        # Group expense lines by (vendor_or_employee_partner, company, currency)
        groups = {}
        
        for expense in self.expense_line_ids:
            # Determine the partner: vendor if specified, otherwise employee
            if expense.expense_vendor_id:
                partner_id = expense.expense_vendor_id.id
                partner_name = expense.expense_vendor_id.name
            else:
                # Use employee's partner
                employee = expense.employee_id or self.employee_id
                partner_id = self._get_employee_partner_id(employee)
                partner_name = employee.name
            
            if not partner_id:
                raise UserError(_(
                    "Cannot determine partner for expense '%s'. "
                    "Please ensure employee has a private address or specify a vendor."
                ) % expense.name)
            
            # Create group key (partner, company, currency)
            group_key = (
                partner_id, 
                expense.company_id.id, 
                expense.currency_id.id
            )
            
            # Initialize group if not exists
            if group_key not in groups:
                groups[group_key] = {
                    'partner_id': partner_id,
                    'partner_name': partner_name,
                    'company_id': expense.company_id.id,
                    'currency_id': expense.currency_id.id,
                    'expenses': self.env['hr.expense'],
                    'is_vendor': bool(expense.expense_vendor_id)
                }
            
            groups[group_key]['expenses'] |= expense
        
        # Create bills for each group
        for group_data in groups.values():
            bill = self._create_single_bill_for_vendor_group(group_data)
            if bill:
                bills |= bill
        
        return bills

    def _create_bills_by_expense_lines(self):
        """Legacy: Group expense lines and create vendor bills per group"""
        bills = self.env['account.move']
        
        # Group expense lines by (vendor_or_employee_partner, company, currency)
        groups = {}
        
        for expense in self.expense_line_ids:
            # Determine the partner based on clear_mode and vendor_id
            partner_id = self._get_partner_for_expense(expense)
            
            if not partner_id:
                # Skip expenses without valid partner
                continue
            
            # Create group key
            group_key = (
                partner_id, 
                expense.company_id.id, 
                expense.currency_id.id
            )
            
            # Validate company and currency consistency
            if group_key not in groups:
                groups[group_key] = {
                    'partner_id': partner_id,
                    'company_id': expense.company_id.id,
                    'currency_id': expense.currency_id.id,
                    'expenses': self.env['hr.expense']
                }
            
            groups[group_key]['expenses'] |= expense
        
        # Create bills for each group
        for group_data in groups.values():
            bill = self._create_single_bill_for_group(group_data)
            if bill:
                bills |= bill
        
        return bills

    def _create_single_bill_for_vendor_group(self, group_data):
        """Create a single vendor bill for a vendor group (enhanced version)"""
        partner_id = group_data['partner_id']
        partner_name = group_data['partner_name']
        company_id = group_data['company_id']
        currency_id = group_data['currency_id']
        expenses = group_data['expenses']
        is_vendor = group_data['is_vendor']
        
        if not partner_id:
            return self.env['account.move']
        
        # Validate company and currency consistency within the group
        for expense in expenses:
            if expense.company_id.id != company_id:
                raise UserError(_(
                    "All expenses in a group must belong to the same company. "
                    "Expense '%s' belongs to a different company."
                ) % expense.name)
            if expense.currency_id.id != currency_id:
                raise UserError(_(
                    "All expenses in a group must use the same currency. "
                    "Expense '%s' uses a different currency."
                ) % expense.name)
        
        # Group expenses by account and taxes to create proper invoice lines
        account_tax_groups = {}
        for expense in expenses:
            account = expense.account_id
            taxes = tuple(expense.tax_ids.ids)
            key = (account.id, taxes)
            
            if key not in account_tax_groups:
                account_tax_groups[key] = {
                    'amount': 0,
                    'expenses': self.env['hr.expense'],
                    'tax_ids': expense.tax_ids.ids,
                    'analytic_account_id': expense.account_analytic_id.id if hasattr(expense, 'account_analytic_id') and expense.account_analytic_id else False,
                    'analytic_tag_ids': expense.analytic_tag_ids.ids if hasattr(expense, 'analytic_tag_ids') else [],
                    'product_id': expense.product_id.id if expense.product_id else False,
                    'wht_tax_id': expense.wht_tax_id.id if hasattr(expense, 'wht_tax_id') and expense.wht_tax_id else False
                }
            
            account_tax_groups[key]['amount'] += expense.total_amount
            account_tax_groups[key]['expenses'] |= expense
        
        # Create vendor bill with grouped lines
        bill_ref = f'Expense Sheet {self.name}'
        if is_vendor:
            bill_ref += f' - {partner_name}'
        else:
            bill_ref += f' - Employee: {partner_name}'
            
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner_id,
            'invoice_date': fields.Date.context_today(self),
            'date': fields.Date.context_today(self),
            'currency_id': currency_id,
            'company_id': company_id,
            'ref': bill_ref,
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
            
            # Handle taxes and amounts properly
            expense_lines = group_data['expenses']
            if len(expense_lines) > 1:
                # Combine amounts from all expenses in this group
                line_vals['name'] = ', '.join(expense_lines.mapped('name'))
            else:
                # Use the single expense details
                single_expense = expense_lines[0]
                line_vals['name'] = single_expense.name
                line_vals['quantity'] = single_expense.quantity if hasattr(single_expense, 'quantity') else 1
                line_vals['price_unit'] = single_expense.unit_amount if hasattr(single_expense, 'unit_amount') and single_expense.unit_amount else single_expense.price_unit
                
            if group_data['analytic_account_id']:
                line_vals['analytic_account_id'] = group_data['analytic_account_id']
            if group_data.get('analytic_tag_ids', []):
                line_vals['analytic_tag_ids'] = [(6, 0, group_data['analytic_tag_ids'])]
            if group_data.get('product_id'):
                line_vals['product_id'] = group_data['product_id']
            if group_data.get('wht_tax_id'):
                line_vals['wht_tax_id'] = group_data['wht_tax_id']
            
            bill_vals['invoice_line_ids'].append((0, 0, line_vals))
        
        bill = self.env['account.move'].create(bill_vals)
        
        # Link advance box to ALL bills when using advance (not just employee bills)
        # This allows WHT wizard to find the correct advance box for vendor bills too
        if self.use_advance and self.advance_box_id:
            bill.sudo().write({
                'advance_box_id': self.advance_box_id.id,
                'is_expense_advance_bill': True
            })
        
        # Carry attachments from expense lines to the bill
        self._carry_attachments_to_bill(expense_lines, bill)
        
        return bill

    def _get_partner_for_expense(self, expense):
        """Get the appropriate partner for an expense based on clear_mode"""
        if self.clear_mode == 'pay_vendor':
            # Use vendor if specified, otherwise skip (will be handled by employee logic)
            return expense.expense_vendor_id.id if expense.expense_vendor_id else False
        elif self.clear_mode == 'mixed':
            # Use vendor if specified, otherwise use employee
            if expense.expense_vendor_id:
                return expense.expense_vendor_id.id
            else:
                employee = expense.employee_id or self.employee_id
                return self._get_employee_partner_id(employee)
        else:  # reimburse_employee
            # Always use employee's private address
            employee = expense.employee_id or self.employee_id
            return self._get_employee_partner_id(employee)

    def _get_employee_partner_id(self, employee):
        """Get the partner ID for an employee (private address)"""
        if not employee:
            return False
            
        partner_id = False
        
        # Method 1: Check if address_home_id exists (from hr_contract module) - Primary method
        if hasattr(employee, 'address_home_id') and employee.sudo().address_home_id:
            partner_id = employee.sudo().address_home_id.id
        
        # Method 2: Get the related user's partner (which might contain private address)
        if not partner_id and employee.user_id and employee.user_id.partner_id:
            partner_id = employee.user_id.partner_id.id
        
        # Method 3: Default to employee's address_id (work address)
        if not partner_id and employee.address_id:
            partner_id = employee.address_id.id
        
        # If still no partner found, try to create/find partner by employee name
        if not partner_id:
            try:
                # ลองหา Partner ที่มีชื่อเดียวกับ Employee ก่อน
                employee_partner = self.env['res.partner'].search([
                    ('name', '=', employee.name),
                    ('is_company', '=', False)
                ], limit=1)
                
                if employee_partner:
                    partner_id = employee_partner.id
                else:
                    # สร้าง Partner ใหม่สำหรับ Employee
                    employee_partner = self.env['res.partner'].create({
                        'name': employee.name,
                        'is_company': False,
                        'employee': True,
                        'supplier_rank': 0,
                        'customer_rank': 0,
                    })
                    partner_id = employee_partner.id
                    
            except Exception as e:
                # Final fallback using all methods
                try:
                    if hasattr(employee, 'address_home_id') and employee.sudo().address_home_id:
                        partner_id = employee.sudo().address_home_id.id
                    elif employee.user_id:
                        partner_id = employee.user_id.partner_id.id
                    elif employee.address_id:
                        partner_id = employee.address_id.id
                except Exception:
                    partner_id = False
        
        return partner_id

    def _create_single_bill_for_group(self, group_data):
        """Create a single vendor bill for a group of expenses"""
        partner_id = group_data['partner_id']
        company_id = group_data['company_id']
        currency_id = group_data['currency_id']
        expenses = group_data['expenses']
        
        if not partner_id:
            return self.env['account.move']
        
        # Validate company and currency consistency within the group
        for expense in expenses:
            if expense.company_id.id != company_id:
                raise UserError(_(
                    "All expenses in a group must belong to the same company. "
                    "Expense '%s' belongs to a different company."
                ) % expense.name)
            if expense.currency_id.id != currency_id:
                raise UserError(_(
                    "All expenses in a group must use the same currency. "
                    "Expense '%s' uses a different currency."
                ) % expense.name)
        
        # Get company for this group
        company = self.env['res.company'].browse(company_id)
        
        # Group expenses by account and taxes to create proper invoice lines
        account_tax_groups = {}
        for expense in expenses:
            account = expense.account_id
            taxes = tuple(expense.tax_ids.ids)
            key = (account.id, taxes)
            
            account_tax_groups[key] = {
                'amount': 0,
                'expenses': self.env['hr.expense'],
                'tax_ids': expense.tax_ids.ids,
                'analytic_account_id': expense.account_analytic_id.id if hasattr(expense, 'account_analytic_id') and expense.account_analytic_id else False,
                'analytic_tag_ids': expense.analytic_tag_ids.ids if hasattr(expense, 'analytic_tag_ids') else [],
                'product_id': expense.product_id.id if expense.product_id else False,
                'wht_tax_id': expense.wht_tax_id.id if hasattr(expense, 'wht_tax_id') and expense.wht_tax_id else False
            }
            
            account_tax_groups[key]['amount'] += expense.total_amount
            account_tax_groups[key]['expenses'] |= expense
        
        # Create vendor bill with grouped lines
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner_id,
            'invoice_date': fields.Date.context_today(self),
            'date': fields.Date.context_today(self),
            'currency_id': currency_id,
            'company_id': company_id,
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
            
            # Handle taxes and amounts properly
            expense_lines = group_data['expenses']
            if len(expense_lines) > 1:
                # Combine amounts from all expenses in this group
                line_vals['name'] = ', '.join(expense_lines.mapped('name'))
            else:
                # Use the single expense details
                single_expense = expense_lines[0]
                line_vals['name'] = single_expense.name
                line_vals['quantity'] = single_expense.quantity if hasattr(single_expense, 'quantity') else 1
                line_vals['price_unit'] = single_expense.unit_amount if hasattr(single_expense, 'unit_amount') and single_expense.unit_amount else single_expense.price_unit  # Use appropriate field to correctly handle taxes
                
            if group_data['analytic_account_id']:
                line_vals['analytic_account_id'] = group_data['analytic_account_id']
            if group_data.get('analytic_tag_ids', []):
                line_vals['analytic_tag_ids'] = [(6, 0, group_data['analytic_tag_ids'])]
            if group_data.get('product_id'):
                line_vals['product_id'] = group_data['product_id']
            # Add WHT tax if available on the expense
            if group_data.get('wht_tax_id'):
                line_vals['wht_tax_id'] = group_data['wht_tax_id']
            
            bill_vals['invoice_line_ids'].append((0, 0, line_vals))
        
        bill = self.env['account.move'].create(bill_vals)
        
        # Carry attachments from expense lines to the bill
        self._carry_attachments_to_bill(expense_lines, bill)
        
        return bill

    def _carry_attachments_to_bill(self, expense_lines, bill):
        """Copy attachments from expense lines to the corresponding bill"""
        Attachment = self.env['ir.attachment']
        
        for expense in expense_lines:
            # Find attachments related to this expense
            expense_attachments = Attachment.search([
                ('res_model', '=', 'hr.expense'),
                ('res_id', '=', expense.id)
            ])
            
            # Copy each attachment to the bill
            for attachment in expense_attachments:
                Attachment.create({
                    'name': attachment.name,
                    'datas': attachment.datas,
                    'res_model': 'account.move',
                    'res_id': bill.id,
                    'type': attachment.type,
                    'url': attachment.url,
                })

    def _post_accounting_activity_for_bills(self, bills):
        """Post accounting activity for reviewers to check the created bills"""
        ICP = self.env['ir.config_parameter'].sudo()
        user_id = int(ICP.get_param('employee_advance.advance_notify_user_id', 0))
        group_id = int(ICP.get_param('employee_advance.advance_notify_group_id', 0))
        activity_type_id = int(ICP.get_param('employee_advance.advance_notify_activity_type_id', 0))
        deadline_days = int(ICP.get_param('employee_advance.advance_notify_deadline_days', 1))
        
        for bill in bills:
            activity_vals = {
                'res_id': bill.id,
                'res_model_id': self.env['ir.model']._get_id('account.move'),
                'activity_type_id': activity_type_id or self.env.ref('employee_advance.mail_activity_type_advance_bill_review').id,
                'summary': f'Review vendor bill for expense sheet {self.name}',
                'user_id': user_id or self.env.ref('base.user_admin').id,
                'date_deadline': fields.Date.add(fields.Date.context_today(self), days=deadline_days),
            }
            
            if group_id:
                activity_vals['user_id'] = self.env['res.users'].search([('groups_id', '=', group_id)], limit=1).id or activity_vals['user_id']
            
            bill.activity_schedule(
                activity_type_id=activity_vals['activity_type_id'],
                summary=activity_vals['summary'],
                note=f"Expense sheet {self.name} has been approved. Please review the vendor bill.",
                user_id=activity_vals['user_id'],
                date_deadline=activity_vals['date_deadline']
            )

    def _validate_expense_lines_for_clear_mode(self):
        """Validate expense lines based on clear_mode"""
        # Temporarily disabled vendor validation
        pass

    def _validate_company_currency_consistency(self):
        """Validate company and currency consistency within sheet"""
        for sheet in self:
            companies = sheet.expense_line_ids.mapped('company_id')
            currencies = sheet.expense_line_ids.mapped('currency_id')
            
            # Note: We can't validate overall sheet consistency here since different groups
            # might have different companies/currencies, but we validate at the group level
            # during bill creation which is already implemented
            
    def _validate_fiscal_period(self):
        """Validate that we're not in a locked fiscal period"""
        for sheet in self:
            company = sheet.company_id
            from odoo import fields
            locked_date = company._get_user_fiscal_lock_date()
            current_date = fields.Date.context_today(sheet)
            if current_date <= locked_date:
                raise UserError(_("Cannot create bills before or during the lock date %s.", locked_date))

    def _validate_advance_box_setup(self):
        """Validate advance box configuration when needed"""
        for sheet in self:
            if sheet.use_advance and sheet.advance_box_id:
                advance_box = sheet.advance_box_id
                if not advance_box.account_id:
                    raise UserError(_("Please set the advance account for the selected advance box."))
                if not advance_box.journal_id:
                    raise UserError(_("Please set the journal for the selected advance box."))

    def action_sheet_paid(self):
        """Override method to handle paid status after advance clearing"""
        # Only change the state to done if not already done
        if self.state != 'done':
            self.write({'state': 'done'})
        return True

    def action_open_wht_clear_advance_wizard(self):
        """Open WHT Clear Advance Wizard - HANG FIX APPLIED v2"""
        import time
        import logging
        
        _logger = logging.getLogger(__name__)
        _logger.info("🎯 WIZARD BUTTON CLICKED: Starting Clear Advance (WHT) for expense sheet %s", self.name)
        
        start_time = time.time()
        self.ensure_one()
        
        # Add immediate response for debugging
        _logger.info("🔍 WIZARD: Method called successfully, processing...")
        
        try:
            _logger.info("🔍 WIZARD: Entering try block...")
            
            # Quick validations
            _logger.info("🔍 WIZARD: Checking use_advance: %s", self.use_advance)
            _logger.info("🔍 WIZARD: Checking advance_box_id: %s", self.advance_box_id.id if self.advance_box_id else 'None')
            _logger.info("🔍 WIZARD: Checking state: %s", self.state)
            
            if not self.use_advance or not self.advance_box_id:
                raise UserError(_("This expense sheet is not using advance or has no advance box configured."))
            
            if self.state != 'approve':
                raise UserError(_("Expense sheet must be approved before clearing advance with WHT."))
            
            # Support cross-employee advance box clearing
            # ให้สามารถ Clear advance box ของพนักงานคนอื่นได้
            if self.advance_box_id.employee_id.id != self.employee_id.id:
                _logger.info("🔄 WIZARD: Cross-employee clearing detected - Current user: %s, Advance box owner: %s", 
                           self.employee_id.name, self.advance_box_id.employee_id.name)
                
                # Use advance box employee's partner information for WHT processing
                advance_box_partner = False
                try:
                    if self.advance_box_id.employee_id.address_home_id:
                        advance_box_partner = self.advance_box_id.employee_id.address_home_id
                    elif self.advance_box_id.employee_id.user_id and self.advance_box_id.employee_id.user_id.partner_id:
                        advance_box_partner = self.advance_box_id.employee_id.user_id.partner_id
                    _logger.info("� WIZARD: Will use advance box employee partner for WHT: %s", 
                               advance_box_partner.name if advance_box_partner else 'None')
                except Exception as e:
                    _logger.warning("⚠️ WIZARD: Could not resolve advance box employee partner: %s", str(e))
                    advance_box_partner = None
                
                # Override partner info if advance box employee partner is found
                if advance_box_partner:
                    employee_partner = advance_box_partner
            
            _logger.info("✅ WIZARD: Basic validations passed")
            
            # Get default employee partner (with timeout protection)
            employee_partner = False
            try:
                if self.employee_id.user_id and self.employee_id.user_id.partner_id:
                    employee_partner = self.employee_id.user_id.partner_id
                elif hasattr(self.employee_id, 'address_home_id') and self.employee_id.address_home_id:
                    employee_partner = self.employee_id.address_home_id
                elif self.employee_id.address_id:
                    employee_partner = self.employee_id.address_id
                _logger.info("💼 WIZARD: Employee partner resolved: %s", employee_partner.name if employee_partner else 'None')
            except Exception as e:
                _logger.warning("⚠️ WIZARD: Could not resolve employee partner: %s", str(e))
                employee_partner = False
            
            # Build context safely - ไม่ส่ง default_partner_id เพื่อให้ wizard หาจาก bill เอง
            context = {
                'default_expense_sheet_id': self.id,
                'default_employee_id': self.employee_id.id,
                'default_advance_box_id': self.advance_box_id.id,
                'default_company_id': self.company_id.id,
                # ไม่ส่ง default_partner_id และ default_wht_partner_id เพื่อให้ wizard หาจาก bill เอง
                # 'default_partner_id': employee_partner.id if employee_partner else False,
                # 'default_wht_partner_id': employee_partner.id if employee_partner else False,
                'default_clear_amount': self.total_amount or 0.0,
                'default_amount_base': self.total_amount or 0.0,
            }
            
            _logger.info("💡 WIZARD: Not sending default partners - letting wizard find vendor from bill")
            
            elapsed = time.time() - start_time
            _logger.info("🚀 WIZARD: Opening wizard (preparation took %.2f seconds)", elapsed)
            
            result = {
                'type': 'ir.actions.act_window',
                'name': _('Clear Advance with WHT'),
                'res_model': 'wht.clear.advance.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': context,
            }
            
            _logger.info("✅ WIZARD: Method completed successfully, returning action")
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.error("❌ WIZARD: Failed to open wizard after %.2f seconds: %s", elapsed, str(e))
            raise UserError(_("Failed to open Clear Advance (WHT) wizard: %s") % str(e))

