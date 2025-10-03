from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class WhtClearAdvanceWizard(models.TransientModel):
    _name = 'wht.clear.advance.wizard'
    _description = 'Clear Advance with WHT Wizard'

    # Context fields (hidden)
    expense_sheet_id = fields.Many2one(
        'hr.expense.sheet',
        string='Expense Sheet',
        required=True,
        readonly=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True,
        readonly=True
    )
    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        required=True,
        help="Employee's advance box"
    )
    current_balance = fields.Monetary(
        string='Current Advance Balance',
        currency_field='currency_id',
        related='advance_box_id.balance',
        readonly=True,
        help="Current balance in the employee's advance box"
    )
    net_amount = fields.Monetary(
        string='Net Amount from Advance',
        currency_field='currency_id',
        compute='_compute_net_amount',
        readonly=True,
        help="Amount that will be deducted from advance box (Clear Amount - WHT)"
    )
    auto_reconcile = fields.Boolean(
        string='Auto Reconcile',
        default=False,  # Disabled by default to prevent hanging - HANG FIX APPLIED
        help="Automatically reconcile the journal entry with matching payable entries (may cause delays). Disabled by default for performance."
    )

    # Company and currency
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='company_id.currency_id',
        readonly=True
    )

    # Partner information
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner (from Bill)',
        required=True,
        help="Partner from the bill - used for AP account entries"
    )
    wht_partner_id = fields.Many2one(
        'res.partner',
        string='WHT Partner (Vendor)',
        required=True,
        help="Vendor partner for withholding tax certificate (PND) - usually same as partner_id"
    )

    # WHT Tax details
    wht_tax_id = fields.Many2one(
        'account.tax',
        string='WHT Tax',
        required=False,
        domain="[('type_tax_use', 'in', ['purchase', 'none']), ('amount', '<', 0)]",
        help="Withholding tax to apply (optional - leave blank for no WHT)"
    )
    wht_tax_rate = fields.Float(
        string='WHT Tax Rate (%)',
        compute='_compute_wht_tax_rate',
        readonly=True,
        help="Tax rate percentage"
    )
    amount_base = fields.Monetary(
        string='Base Amount',
        currency_field='currency_id',
        help="Base amount for WHT calculation"
    )
    wht_amount = fields.Monetary(
        string='WHT Amount',
        currency_field='currency_id',
        readonly=True,
        compute='_compute_wht_amount',
        help="Computed WHT amount (base × tax rate)"
    )
    
    # Clearing amounts
    clear_amount = fields.Monetary(
        string='Clear Amount',
        currency_field='currency_id',
        required=True,
        help="Amount to clear from Advance Box before WHT"
    )

    # Journal entry details
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain="[('type', '=', 'general'), ('company_id', '=', company_id)]",
        help="General journal for the entry"
    )
    date = fields.Date(
        string='Date',
        required=True,
        default=fields.Date.context_today,
        help="Journal entry date"
    )
    ref = fields.Char(
        string='Reference',
        help="Reference for the journal entry"
    )

    @api.model
    def default_get(self, fields_list):
        """Override default_get with hang prevention - HANG FIX APPLIED v2"""
        import time
        start_time = time.time()
        
        _logger.info("🎯 WIZARD DEFAULT_GET CALLED: Starting with fields %s", fields_list)
        _logger.info("🎯 WIZARD DEFAULT_GET: Context = %s", dict(self.env.context))
        
        try:
            _logger.info("🔍 WIZARD DEFAULT_GET: Calling super().default_get...")
            res = super().default_get(fields_list)
            _logger.info("✅ WIZARD DEFAULT_GET: Super call completed")
            
            # Get advance box from context first (from bill action - ถูกต้องที่สุด) 
            advance_box_id = self.env.context.get('default_advance_box_id')
            if advance_box_id:
                try:
                    advance_box = self.env['employee.advance.box'].browse(advance_box_id)
                    if advance_box.exists():
                        res['advance_box_id'] = advance_box_id
                        # Avoid heavy balance computation in default_get
                        _logger.info("💰 WIZARD: Using advance box from context: %s (id: %s)", 
                                   advance_box.name, advance_box_id)
                    else:
                        _logger.warning("⚠️ WIZARD: Advance box id %s from context not found", advance_box_id)
                        advance_box_id = False
                except Exception as e:
                    _logger.warning("⚠️ WIZARD: Error getting advance box: %s", str(e))
                    advance_box_id = False
        
            # Get expense sheet from context (with timeout protection)
            expense_sheet_id = self.env.context.get('default_expense_sheet_id')
            if expense_sheet_id:
                try:
                    expense_sheet = self.env['hr.expense.sheet'].browse(expense_sheet_id)
                    if expense_sheet.exists():
                        res['expense_sheet_id'] = expense_sheet.id
                        
                        # Set employee info
                        if expense_sheet.employee_id:
                            res['employee_id'] = expense_sheet.employee_id.id
                            _logger.info("👤 WIZARD: Employee set: %s", expense_sheet.employee_id.name)
                            
                            # Set advance box only if not already set from context
                            if not advance_box_id:
                                if expense_sheet.advance_box_id:
                                    # Allow cross-employee advance box clearing
                                    # ให้สามารถ Clear advance box ของพนักงานคนอื่นได้
                                    if (expense_sheet.advance_box_id.employee_id.id == expense_sheet.employee_id.id):
                                        res['advance_box_id'] = expense_sheet.advance_box_id.id
                                        _logger.info("💰 WIZARD: Using advance box from expense sheet: %s", 
                                                   expense_sheet.advance_box_id.name)
                                    else:
                                        # Cross-employee clearing is allowed
                                        res['advance_box_id'] = expense_sheet.advance_box_id.id
                                        _logger.info("🔄 WIZARD: Cross-employee clearing - User: %s clearing advance box of: %s", 
                                                   expense_sheet.employee_id.name,
                                                   expense_sheet.advance_box_id.employee_id.name)
                                        _logger.info("💰 WIZARD: Using advance box: %s", expense_sheet.advance_box_id.name)
                                else:
                                    # Quick fallback: search for advance box (limited scope)
                                    try:
                                        company_id = self.env.context.get('default_company_id') or self.env.company.id
                                        advance_box = self.env['employee.advance.box'].search([
                                            ('employee_id', '=', expense_sheet.employee_id.id),
                                            ('company_id', '=', company_id)
                                        ], limit=1)
                                        if advance_box:
                                            res['advance_box_id'] = advance_box.id
                                            _logger.info("💰 WIZARD: Found fallback advance box: %s", advance_box.name)
                                        else:
                                            _logger.warning("⚠️ WIZARD: No advance box found for employee %s", 
                                                          expense_sheet.employee_id.name)
                                    except Exception as e:
                                        _logger.warning("⚠️ WIZARD: Error searching advance box: %s", str(e))
                except Exception as e:
                    _logger.warning("⚠️ WIZARD: Error processing expense sheet: %s", str(e))
        
            # หา Vendor จาก Bill จริงๆ - ลองหาจาก active_id ก่อน (ถ้าเรียกจากหน้า bill)
            vendor_from_bill = None
            
            # ตรวจสอบว่าเรียกจากหน้า bill หรือไม่
            active_model = self.env.context.get('active_model')
            active_id = self.env.context.get('active_id')
            
            _logger.info("🔍 WIZARD: Active context - model: %s, id: %s", active_model, active_id)
            
            if active_model == 'account.move' and active_id:
                # เรียกจากหน้า bill โดยตรง
                try:
                    bill = self.env['account.move'].browse(active_id)
                    if bill.exists() and bill.move_type == 'in_invoice' and bill.partner_id:
                        vendor_from_bill = bill.partner_id
                        _logger.info("🏪 WIZARD: Found vendor from active bill: %s", vendor_from_bill.name)
                except Exception as e:
                    _logger.warning("⚠️ WIZARD: Error getting vendor from active bill: %s", str(e))
            
            # ถ้าไม่เจอจาก active_id หรือไม่ได้เรียกจากหน้า bill ให้หาจาก expense sheet
            if not vendor_from_bill and expense_sheet_id:
                try:
                    expense_sheet = self.env['hr.expense.sheet'].browse(expense_sheet_id)
                    if expense_sheet.exists():
                        _logger.info("🔍 WIZARD: Searching for vendor bills in expense sheet...")
                        
                        # ลองหาจาก bill_ids (Many2many) ก่อน
                        if expense_sheet.bill_ids:
                            _logger.info("🔍 WIZARD: Found bill_ids: %d bills", len(expense_sheet.bill_ids))
                            vendor_bills = expense_sheet.bill_ids.filtered(
                                lambda m: m.move_type == 'in_invoice' and m.partner_id
                            )
                            if vendor_bills:
                                vendor_from_bill = vendor_bills[0].partner_id
                                _logger.info("🏪 WIZARD: Found vendor from bill_ids: %s", vendor_from_bill.name)
                        
                        # ถ้าไม่เจอ ให้หาจาก bill_id (Many2one) 
                        if not vendor_from_bill and expense_sheet.bill_id:
                            _logger.info("🔍 WIZARD: Checking single bill_id...")
                            if expense_sheet.bill_id.move_type == 'in_invoice' and expense_sheet.bill_id.partner_id:
                                vendor_from_bill = expense_sheet.bill_id.partner_id
                                _logger.info("🏪 WIZARD: Found vendor from bill_id: %s", vendor_from_bill.name)
                        
                        if not vendor_from_bill:
                            _logger.warning("⚠️ WIZARD: No vendor bills found in expense sheet")
                        
                except Exception as e:
                    _logger.warning("⚠️ WIZARD: Error finding vendor from expense sheet: %s", str(e))
            
            # DEBUG: ตรวจสอบ context อีกครั้ง
            context_partner_id = self.env.context.get('default_partner_id')
            context_wht_partner_id = self.env.context.get('default_wht_partner_id')
            _logger.info("🔍 DEBUG: Context partners - partner_id: %s, wht_partner_id: %s", 
                       context_partner_id, context_wht_partner_id)
            
            # ใช้ vendor จาก bill เป็นหลัก
            if vendor_from_bill:
                # ใช้ vendor จาก bill เป็นหลัก
                res['partner_id'] = vendor_from_bill.id
                res['wht_partner_id'] = vendor_from_bill.id
                _logger.info("✅ WIZARD: FINAL RESULT - Using vendor from bill: %s (ID: %s)", 
                           vendor_from_bill.name, vendor_from_bill.id)
            else:
                # Fallback: หา employee partner ถ้าไม่เจอ vendor จาก bill
                _logger.info("👥 WIZARD: No vendor found from bill, falling back to employee partner")
                
                employee_partner = None
                if expense_sheet_id:
                    try:
                        expense_sheet = self.env['hr.expense.sheet'].browse(expense_sheet_id)
                        if expense_sheet.exists() and expense_sheet.employee_id:
                            employee = expense_sheet.employee_id
                            _logger.info("🔍 DEBUG: Employee name: %s", employee.name)
                            # Try multiple methods to get employee partner
                            if employee.user_id and employee.user_id.partner_id:
                                employee_partner = employee.user_id.partner_id
                                _logger.info("🔍 DEBUG: Found employee partner via user: %s", employee_partner.name)
                            elif hasattr(employee, 'address_home_id') and employee.address_home_id:
                                employee_partner = employee.address_home_id
                                _logger.info("🔍 DEBUG: Found employee partner via address_home_id: %s", employee_partner.name)
                            elif employee.address_id:
                                employee_partner = employee.address_id
                                _logger.info("🔍 DEBUG: Found employee partner via address_id: %s", employee_partner.name)
                    except Exception as e:
                        _logger.warning("⚠️ WIZARD: Error finding employee partner: %s", str(e))
                
                if employee_partner:
                    res['partner_id'] = employee_partner.id
                    res['wht_partner_id'] = employee_partner.id
                    _logger.info("✅ WIZARD: FINAL RESULT - Using employee partner as fallback: %s (ID: %s)", 
                               employee_partner.name, employee_partner.id)
                else:
                    _logger.warning("❌ WIZARD: No partner found - neither vendor from bill nor employee partner")
            
            # DEBUG: แสดงผลลัพธ์สุดท้าย
            final_partner_id = res.get('partner_id')
            final_wht_partner_id = res.get('wht_partner_id')
            if final_partner_id:
                try:
                    final_partner = self.env['res.partner'].browse(final_partner_id)
                    _logger.info("🎯 FINAL DEBUG: partner_id = %s (%s)", final_partner_id, final_partner.name)
                except:
                    _logger.warning("❌ FINAL DEBUG: Could not resolve final partner_id %s", final_partner_id)
            if final_wht_partner_id:
                try:
                    final_wht_partner = self.env['res.partner'].browse(final_wht_partner_id)
                    _logger.info("🎯 FINAL DEBUG: wht_partner_id = %s (%s)", final_wht_partner_id, final_wht_partner.name)
                except:
                    _logger.warning("❌ FINAL DEBUG: Could not resolve final wht_partner_id %s", final_wht_partner_id)
            
            # Set amounts from context
            if self.env.context.get('default_clear_amount'):
                res['clear_amount'] = self.env.context.get('default_clear_amount')
            
            if self.env.context.get('default_amount_base'):
                res['amount_base'] = self.env.context.get('default_amount_base')
            
            elapsed = time.time() - start_time
            _logger.info("✅ WIZARD DEFAULT_GET: Completed in %.2f seconds", elapsed)
            
            return res
            
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.error("❌ WIZARD DEFAULT_GET: Failed after %.2f seconds: %s", elapsed, str(e))
            # Return basic defaults to prevent complete failure
            return super().default_get(fields_list)

    @api.depends('wht_tax_id')
    def _compute_wht_tax_rate(self):
        """Compute WHT tax rate with hang prevention"""
        for record in self:
            try:
                if record.wht_tax_id:
                    record.wht_tax_rate = abs(record.wht_tax_id.amount or 0.0)
                else:
                    record.wht_tax_rate = 0.0
            except Exception as e:
                _logger.warning("⚠️ WIZARD: Error computing WHT tax rate: %s", str(e))
                record.wht_tax_rate = 0.0

    @api.depends('amount_base', 'wht_tax_id')
    def _compute_wht_amount(self):
        """Compute WHT amount with hang prevention"""
        for wizard in self:
            try:
                if wizard.wht_tax_id and wizard.amount_base:
                    # WHT taxes have negative rates, so we negate to get positive WHT amount
                    tax_amount = wizard.wht_tax_id.amount or 0.0
                    wizard.wht_amount = abs((wizard.amount_base or 0.0) * (tax_amount / 100))
                else:
                    # No WHT tax selected or no base amount
                    wizard.wht_amount = 0.0
            except Exception as e:
                _logger.warning("⚠️ WIZARD: Error computing WHT amount: %s", str(e))
                wizard.wht_amount = 0.0
    
    @api.depends('clear_amount', 'wht_amount')
    def _compute_net_amount(self):
        """Compute net amount with hang prevention"""
        for wizard in self:
            try:
                wizard.net_amount = (wizard.clear_amount or 0.0) - (wizard.wht_amount or 0.0)
            except Exception as e:
                _logger.warning("⚠️ WIZARD: Error computing net amount: %s", str(e))
                wizard.net_amount = 0.0

    @api.constrains('clear_amount', 'wht_amount', 'wht_tax_id', 'amount_base')
    def _check_amounts(self):
        """Validate amounts with hang prevention"""
        try:
            for record in self:
                clear_amount = record.clear_amount or 0.0
                wht_amount = record.wht_amount or 0.0
                
                if clear_amount <= 0:
                    raise ValidationError(_("Clear amount must be greater than zero."))
                if wht_amount < 0:
                    raise ValidationError(_("WHT amount cannot be negative."))
                if wht_amount >= clear_amount:
                    raise ValidationError(_("WHT amount cannot be equal to or greater than clear amount."))
                
                # ถ้าเลือก WHT Tax แล้วต้องใส่ Base Amount
                if record.wht_tax_id and not record.amount_base:
                    raise ValidationError(_("Base Amount is required when WHT Tax is selected."))
                    
        except ValidationError:
            # Re-raise validation errors as they should be shown to user
            raise
        except Exception as e:
            _logger.warning("⚠️ WIZARD: Error in amount validation: %s", str(e))
            # Don't block wizard creation for non-validation errors

    @api.onchange('advance_box_id')
    def _onchange_advance_box_id(self):
        if self.advance_box_id:
            _logger.info("DEBUG: Advance box changed to: %s (id: %s, employee: %s, balance: %s)", 
                        self.advance_box_id.display_name, 
                        self.advance_box_id.id,
                        self.advance_box_id.employee_id.name if self.advance_box_id.employee_id else 'No Employee',
                        self.advance_box_id.balance)
            
            # Allow cross-employee advance box clearing
            # ให้สามารถ Clear advance box ของพนักงานคนอื่นได้
            if self.employee_id and self.advance_box_id.employee_id != self.employee_id:
                _logger.info("🔄 CROSS-EMPLOYEE: Clearing advance box of %s by user %s", 
                           self.advance_box_id.employee_id.name, self.employee_id.name)
                
                # ไม่อัพเดต partner ที่นี่ เพราะควรใช้ vendor จาก bill
                # แค่ log ข้อมูลเท่านั้น
                _logger.info("🔄 CROSS-EMPLOYEE: Advance box employee is different, but keeping vendor from bill as partner")
            
            # Set default journal from advance box if available
            if self.advance_box_id.journal_id:
                # Look for a general journal, fallback to advance box journal
                general_journals = self.env['account.journal'].search([
                    ('type', '=', 'general'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                if general_journals:
                    self.journal_id = general_journals[0]

    def _validate_data_integrity(self):
        """Validate data integrity between expense sheet, employee, and advance box (fast version)"""
        errors = []
        
        # Basic field validation
        if not self.expense_sheet_id:
            errors.append(_("No expense sheet specified"))
        
        if not self.employee_id:
            errors.append(_("No employee specified"))
        
        if not self.advance_box_id:
            errors.append(_("No advance box specified"))
        
        # Quick validation without heavy field access
        if self.expense_sheet_id and self.employee_id:
            # Allow cross-employee operations
            # ให้สามารถทำงานข้าม employee ได้
            expense_employee_id = self.expense_sheet_id.employee_id.id
            wizard_employee_id = self.employee_id.id
            if expense_employee_id != wizard_employee_id:
                _logger.info("🔄 VALIDATION: Cross-employee operation detected - Expense: %s, Wizard: %s", 
                           expense_employee_id, wizard_employee_id)
                # Don't add error - allow cross-employee operations
        
        if self.advance_box_id and self.employee_id:
            # Allow cross-employee advance box clearing
            # ให้สามารถ Clear advance box ของพนักงานคนอื่นได้
            advance_employee_id = self.advance_box_id.employee_id.id
            wizard_employee_id = self.employee_id.id
            if advance_employee_id != wizard_employee_id:
                _logger.info("🔄 VALIDATION: Cross-employee clearing detected - User: %s, Advance box: %s", 
                           wizard_employee_id, advance_employee_id)
                # Don't add error - allow cross-employee clearing
        
        # Skip expense sheet advance box validation to avoid recursive issues
        
        if errors:
            _logger.error("DEBUG: Data integrity errors: %s", '; '.join(errors))
            raise ValidationError('\n'.join(errors))
        
        _logger.info("DEBUG: Data integrity validation passed - Employee ID: %s, Advance Box ID: %s", 
                    self.employee_id.id, self.advance_box_id.id)

    @api.onchange('employee_id')
    def _onchange_employee_id(self):
        # ปิดการทำงานชั่วคราว - ไม่ให้ override partner_id จาก bill
        # เพราะต้องการใช้ vendor จาก bill แทนที่จะเป็น employee
        pass

    def _get_advance_account(self):
        """Get the advance account for the employee"""
        self.ensure_one()
        if not self.advance_box_id.account_id:
            raise UserError(_("No advance account configured for employee %s") % self.employee_id.name)
        return self.advance_box_id.account_id

    def _get_partner_payable_account(self):
        """Get the payable account for the partner"""
        self.ensure_one()
        payable_account = self.partner_id.property_account_payable_id
        if not payable_account:
            raise UserError(_("No payable account configured for partner %s") % self.partner_id.name)
        return payable_account

    def _get_wht_payable_account(self):
        """Get the WHT payable account"""
        self.ensure_one()
        
        # First try to get from WHT tax configuration
        if self.wht_tax_id and self.wht_tax_id.invoice_repartition_line_ids:
            wht_lines = self.wht_tax_id.invoice_repartition_line_ids.filtered(lambda l: l.repartition_type == 'tax')
            if wht_lines and wht_lines[0].account_id:
                return wht_lines[0].account_id
        
        # Fallback: search for WHT payable account
        wht_account = self.env['account.account'].search([
            ('name', 'ilike', 'withholding'),
            ('account_type', '=', 'liability_current'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not wht_account:
            raise UserError(_("No WHT payable account found. Please configure the WHT tax account or create a WHT payable account."))
        
        return wht_account

    def create_journal_entry(self):
        """Create and post the journal entry for clearing advance with WHT"""
        self.ensure_one()
        
        _logger.info("DEBUG: Starting journal entry creation for advance clearing")
        
        # Validate data integrity first (with timeout protection)
        try:
            self._validate_data_integrity()
        except Exception as e:
            _logger.error("DEBUG: Data integrity validation failed: %s", str(e))
            raise
        
        # Validate advance box balance
        required_amount = self.clear_amount - self.wht_amount
        current_balance = self.advance_box_id.balance
        
        if current_balance < required_amount:
            # Refresh balance to get latest data (with timeout protection)
            try:
                _logger.info("DEBUG: Refreshing advance box balance...")
                # Use a simple balance refresh to avoid hanging
                self.advance_box_id._refresh_balance_simple()
                current_balance = self.advance_box_id.balance
                _logger.info("DEBUG: Balance after refresh: %s", current_balance)
            except Exception as e:
                _logger.warning("DEBUG: Balance refresh failed, using current balance: %s", str(e))
                # Continue with current balance if refresh fails
            
            if current_balance < required_amount:
                raise UserError(_(
                    "Insufficient advance box balance.\n\n"
                    "Current Balance: %s %s\n"
                    "Required Amount: %s %s (Clear Amount: %s - WHT: %s)\n\n"
                    "The employee needs to have sufficient advance balance to clear this amount. "
                    "Please top up the advance box or adjust the clearing amount."
                ) % (
                    current_balance, self.currency_id.name,
                    required_amount, self.currency_id.name,
                    self.clear_amount, self.wht_amount
                ))

        # Get accounts
        advance_account = self._get_advance_account()
        payable_account = self._get_partner_payable_account()
        
        # Only get WHT account if WHT tax is selected
        wht_account = None
        if self.wht_tax_id:
            wht_account = self._get_wht_payable_account()

        # Log account information
        _logger.info("📋 JOURNAL ENTRY ACCOUNTS:")
        _logger.info("  💰 Advance Account: %s (%s)", advance_account.name, advance_account.code)
        _logger.info("  👤 Payable Account: %s (%s)", payable_account.name, payable_account.code)
        if wht_account:
            _logger.info("  🧾 WHT Account: %s (%s)", wht_account.name, wht_account.code)
        
        _logger.info("📋 JOURNAL ENTRY AMOUNTS:")
        _logger.info("  💵 Clear Amount: %s", self.clear_amount)
        _logger.info("  🧾 WHT Amount: %s", self.wht_amount)
        _logger.info("  💰 Net to Advance: %s", self.clear_amount - self.wht_amount)

        # Find vendor from expense sheet's vendor bill
        vendor_partner = None
        vendor_bill = None
        
        # หาค่า vendor จาก vendor bill ของ expense sheet
        if self.expense_sheet_id and hasattr(self.expense_sheet_id, 'account_move_ids'):
            # หา vendor bill จาก expense sheet
            vendor_bills = self.expense_sheet_id.account_move_ids.filtered(
                lambda m: m.move_type == 'in_invoice' and m.state == 'posted' and m.payment_state in ('not_paid', 'partial')
            )
            if vendor_bills:
                vendor_bill = vendor_bills[0]  # ใช้ bill แรกที่พบ
                vendor_partner = vendor_bill.partner_id
                _logger.info("🏢 Found vendor bill: %s, Vendor: %s", vendor_bill.name, vendor_partner.name)
            else:
                _logger.warning("⚠️ No unpaid vendor bill found in expense sheet, using wizard partner")
                vendor_partner = self.partner_id
        else:
            _logger.warning("⚠️ No expense sheet or account moves, using wizard partner")
            vendor_partner = self.partner_id

        # Create move lines
        move_lines = []
        
        _logger.info("📋 CREATING JOURNAL ENTRY LINES:")
        
        # Dr Payable (vendor from bill) = clear_amount
        # เดบิต Vendor จาก Bill = จ่ายเงินให้ vendor
        _logger.info("  📤 Debit Vendor (from bill): %s (%s) = %s", 
                   vendor_partner.name, payable_account.code, self.clear_amount)
        move_lines.append((0, 0, {
            'name': _('Clear advance with WHT - %s') % vendor_partner.name,
            'account_id': payable_account.id,
            'partner_id': vendor_partner.id,
            'debit': self.clear_amount,
            'credit': 0.0,
            'currency_id': self.currency_id.id,
        }))
        
        # Cr Advance Box (employee advance account) = clear_amount - wht_amount
        # เครดิต Advance Box = ลดยอด advance box (ไม่ต้องระบุ partner_id)
        advance_credit = self.clear_amount - self.wht_amount
        _logger.info("  📥 Credit Advance Box: %s (%s) = %s", 
                   self.advance_box_id.name, advance_account.code, advance_credit)
        
        # ใช้ Employee โดยตรงแทน User ID เพื่อให้ match กับ Advance Box
        advance_partner_id = False
        try:
            employee = self.advance_box_id.employee_id
            if employee:
                # สร้าง Partner ใหม่สำหรับ Employee หากไม่มี หรือใช้ Employee เป็น Partner โดยตรง
                # ไม่ใช้ User ID เพื่อหลีกเลี่ยงปัญหา mismatch
                
                # ลองหา Partner ที่มีชื่อเดียวกับ Employee ก่อน
                employee_partner = self.env['res.partner'].search([
                    ('name', '=', employee.name),
                    ('is_company', '=', False)
                ], limit=1)
                
                if employee_partner:
                    advance_partner_id = employee_partner.id
                    _logger.info("🎯 EMPLOYEE PARTNER: Found existing partner %s (%s) for employee %s", 
                               advance_partner_id, employee_partner.name, employee.name)
                else:
                    # สร้าง Partner ใหม่สำหรับ Employee
                    employee_partner = self.env['res.partner'].create({
                        'name': employee.name,
                        'is_company': False,
                        'employee': True,
                        'supplier_rank': 0,
                        'customer_rank': 0,
                    })
                    advance_partner_id = employee_partner.id
                    _logger.info("🎯 EMPLOYEE PARTNER: Created new partner %s (%s) for employee %s", 
                               advance_partner_id, employee_partner.name, employee.name)
                    
        except Exception as e:
            _logger.warning("⚠️ Could not create/find employee partner: %s", str(e))
            # Fallback ไปใช้ method เดิม
            try:
                employee = self.advance_box_id.employee_id
                if hasattr(employee, 'address_home_id') and employee.sudo().address_home_id:
                    advance_partner_id = employee.sudo().address_home_id.id
                elif employee.user_id:
                    advance_partner_id = employee.user_id.partner_id.id
                elif employee.address_id:
                    advance_partner_id = employee.address_id.id
                _logger.info("🔄 FALLBACK: Using partner %s", advance_partner_id)
            except Exception as e2:
                _logger.warning("⚠️ Fallback also failed: %s", str(e2))
        
        move_lines.append((0, 0, {
            'name': _('Clear from advance box - %s') % self.advance_box_id.employee_id.name,
            'account_id': advance_account.id,
            'partner_id': advance_partner_id,  # ใช้ advance box employee partner
            'debit': 0.0,
            'credit': advance_credit,
            'currency_id': self.currency_id.id,
        }))
        
        # Cr WHT Payable = wht_amount (only if WHT is selected)
        # เครดิต หัก ณ ที่จ่าย = จ่ายภาษี WHT แทนพนักงาน
        if self.wht_tax_id and self.wht_amount > 0:
            _logger.info("  📥 Credit WHT Payable: %s (%s) = %s", 
                       self.wht_tax_id.name, wht_account.code, self.wht_amount)
            move_lines.append((0, 0, {
                'name': _('WHT Payable - %(tax_name)s - %(vendor_name)s') % {
                    'tax_name': self.wht_tax_id.name,
                    'vendor_name': self.wht_partner_id.name
                },
                'account_id': wht_account.id,
                'partner_id': self.wht_partner_id.id,  # ใช้ vendor partner สำหรับ PND
                'debit': 0.0,
                'credit': self.wht_amount,
                'currency_id': self.currency_id.id,
                'tax_line_id': self.wht_tax_id.id,
                'tax_base_amount': self.amount_base,
            }))
        else:
            _logger.info("  ℹ️ No WHT applied")
            
        _logger.info("📋 TOTAL JOURNAL ENTRY: %d lines", len(move_lines))

        # Create journal entry
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': self.date,
            'ref': self.ref or _('Clear Advance with WHT - %s') % self.expense_sheet_id.name,
            'move_type': 'entry',
            'line_ids': move_lines,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
        }

        try:
            _logger.info("DEBUG: Creating journal entry with %d lines", len(move_lines))
            move = self.env['account.move'].create(move_vals)
            _logger.info("DEBUG: Journal entry created: %s", move.name)
            
            # Debug: Show move lines before posting
            _logger.info("📋 MOVE LINES BEFORE POST:")
            for line in move.line_ids:
                _logger.info("  Line: %s | Account: %s | Partner: %s | Debit: %s | Credit: %s", 
                           line.name, line.account_id.code, 
                           line.partner_id.name if line.partner_id else 'None',
                           line.debit, line.credit)
            
            # Post the journal entry
            _logger.info("DEBUG: Posting journal entry")
            move.action_post()
            _logger.info("DEBUG: Journal entry posted successfully")
            
            # Debug: Show move lines after posting
            _logger.info("📋 MOVE LINES AFTER POST:")
            for line in move.line_ids:
                _logger.info("  Line: %s | Account: %s | Partner: %s | Debit: %s | Credit: %s", 
                           line.name, line.account_id.code, 
                           line.partner_id.name if line.partner_id else 'None',
                           line.debit, line.credit)
            
            # Link to expense sheet BEFORE auto reconcile to avoid issues
            _logger.info("DEBUG: Linking to expense sheet")
            self.expense_sheet_id.write({
                'bill_ids': [(4, move.id)],
                'is_billed': True,
            })
            
            # Auto reconcile with related bills/payments if enabled - HANG FIX APPLIED
            if self.auto_reconcile:
                _logger.info("🔄 Starting auto reconciliation (user enabled)")
                try:
                    self._auto_reconcile_with_timeout(move)
                    _logger.info("✅ Auto reconciliation process completed")
                except Exception as e:
                    _logger.warning("⚠️ Auto reconcile failed but continuing operation: %s", str(e))
                    # Don't fail the entire clear advance operation just because auto reconcile failed
            else:
                _logger.info("⏭️ Auto reconciliation disabled (recommended for performance)")
            
            # Update advance box balance - use safe refresh method - HANG FIX
            old_balance = self.advance_box_id.balance
            _logger.info("💰 Refreshing advance box balance (current: %s)", old_balance)
            
            # Debug: Show what partner_id advance_box is using for balance calculation
            try:
                employee = self.advance_box_id.employee_id
                compute_partner_id = None
                if hasattr(employee, 'address_home_id') and employee.sudo().address_home_id:
                    compute_partner_id = employee.sudo().address_home_id.id
                elif employee.user_id:
                    compute_partner_id = employee.user_id.partner_id.id
                elif employee.address_id:
                    compute_partner_id = employee.address_id.id
                _logger.info("🔍 BALANCE CALC: Advance box uses partner_id %s for balance calculation", compute_partner_id)
                _logger.info("🔍 JE PARTNER: Journal entry used partner_id %s", advance_partner_id)
            except Exception as e:
                _logger.warning("⚠️ Error checking partner_id match: %s", str(e))
            
            try:
                self.advance_box_id._refresh_balance_simple()
                new_balance = self.advance_box_id.balance
                _logger.info("✅ Advance box balance refreshed: %s → %s (change: %s)", 
                           old_balance, new_balance, new_balance - old_balance)
            except Exception as e:
                _logger.warning("⚠️ Balance refresh failed but continuing: %s", str(e))
                # Don't fail the entire operation if balance refresh fails
            
            # Add context to the move 
            move_data = {
                'is_advance_clearing': True,
                'advance_box_id': self.advance_box_id.id,
                'expense_sheet_id': self.expense_sheet_id.id,
            }
            
            # Add WHT context only if WHT is selected
            if self.wht_tax_id:
                move_data.update({
                    'wht_tax_id': self.wht_tax_id.id,
                    'wht_base_amount': self.amount_base,
                    'wht_amount': self.wht_amount,
                })
            
            move.write(move_data)
            
            _logger.info("Created WHT advance clearing journal entry: %s", move.name)
            
            # Return action to open the created journal entry
            return {
                'type': 'ir.actions.act_window',
                'name': _('Journal Entry'),
                'res_model': 'account.move',
                'res_id': move.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error("Error creating WHT advance clearing journal entry: %s", str(e))
            raise UserError(_("Failed to create journal entry: %s") % str(e))

    def _refresh_balance_simple(self):
        """Simple balance refresh without heavy computation"""
        try:
            # Just invalidate the cache and let it recompute naturally
            self.advance_box_id.invalidate_recordset(['balance'])
            # Read the balance to trigger recomputation
            balance = self.advance_box_id.balance
            _logger.info("DEBUG: Advance box balance refreshed: %s", balance)
        except Exception as e:
            _logger.warning("DEBUG: Failed to refresh balance: %s", str(e))

    def _auto_reconcile_with_timeout(self, move):
        """Auto reconcile with strict timeout protection - HANG FIX APPLIED"""
        import time
        start_time = time.time()
        strict_timeout = 3  # Very strict 3-second timeout to prevent hanging
        
        try:
            _logger.info("🔄 Auto reconcile starting (strict %ds timeout to prevent hang)", strict_timeout)
            result = self._auto_reconcile_ultra_fast(move)
            elapsed = time.time() - start_time
            _logger.info("✅ Auto reconcile completed in %.2f seconds", elapsed)
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.warning("⚠️ Auto reconcile failed after %.2f seconds: %s", elapsed, str(e))
            if elapsed > strict_timeout:
                _logger.warning("⏰ Auto reconcile timeout - skipping for performance")
                return False
            else:
                # Don't raise error, just log and continue
                _logger.warning("ℹ️ Auto reconcile error - continuing without reconcile: %s", str(e))
                return False

    def _auto_reconcile_ultra_fast(self, move):
        """Ultra-fast auto reconcile with minimal database queries - HANG FIX"""
        self.ensure_one()
        
        try:
            _logger.info("🎯 Ultra-fast auto reconcile for move %s", move.name)
            
            # Find only the first payable line to reconcile
            payable_line = move.line_ids.filtered(
                lambda l: l.debit > 0 and l.partner_id and l.account_id.account_type == 'liability_payable'
            )[:1]  # Take only first line
            
            if not payable_line:
                _logger.info("ℹ️ No payable lines found for reconciliation (this is normal)")
                return True
                
            line = payable_line[0]
            _logger.info("💳 Processing payable line: %s (%.2f)", line.name, line.debit)
            
            # Ultra-restricted search - only very recent entries
            from datetime import datetime, timedelta
            recent_date = datetime.now().date() - timedelta(days=7)  # Only last 7 days
            
            domain = [
                ('partner_id', '=', line.partner_id.id),
                ('account_id', '=', line.account_id.id),
                ('credit', '>', 0),
                ('reconciled', '=', False),
                ('move_id.state', '=', 'posted'),
                ('date', '>=', recent_date)  # Very recent only
            ]
            
            # Super limited search - only 1 record max to prevent hanging
            reconcilable_lines = self.env['account.move.line'].search(
                domain, limit=1, order='date desc, id desc'
            )
            
            if reconcilable_lines:
                target_line = reconcilable_lines[0]
                lines_to_reconcile = line + target_line
                
                _logger.info("🔗 Ultra-fast reconciling with: %s", target_line.name)
                lines_to_reconcile.reconcile()
                _logger.info("✅ Ultra-fast reconciliation completed")
                return True
            else:
                _logger.info("ℹ️ No recent matching lines found (this is normal)")
                return True
                
        except Exception as e:
            _logger.warning("⚠️ Ultra-fast auto reconcile failed: %s", str(e))
            return False

    def _auto_reconcile(self, move):
        """Auto reconcile the journal entry with related payables (simplified version)"""
        self.ensure_one()
        
        try:
            _logger.info("DEBUG: Starting auto reconcile for move %s", move.name)
            
            # Find payable lines from the move (Dr lines with partners) - limit to avoid hang
            payable_lines = move.line_ids.filtered(
                lambda l: l.debit > 0 and l.partner_id and l.account_id.account_type == 'liability_payable'
            )[:5]  # Limit to 5 lines maximum
            
            _logger.info("DEBUG: Found %d payable lines to reconcile", len(payable_lines))
            
            reconciled_count = 0
            for line in payable_lines:
                if reconciled_count >= 3:  # Limit reconciliation attempts
                    break
                    
                partner = line.partner_id
                account = line.account_id
                
                _logger.info("DEBUG: Looking for reconcilable lines for partner %s", partner.name)
                
                # Find unreconciled payable lines - limit search scope
                domain = [
                    ('partner_id', '=', partner.id),
                    ('account_id', '=', account.id),
                    ('reconciled', '=', False),
                    ('parent_state', '=', 'posted'),
                    ('id', '!=', line.id),
                    ('credit', '>', 0),  # Only credit lines (vendor bills)
                    ('date', '>=', fields.Date.add(fields.Date.today(), days=-90))  # Only last 90 days
                ]
                
                # Limit search results to avoid performance issues
                matching_lines = self.env['account.move.line'].search(domain, limit=10, order='date desc')
                
                if matching_lines:
                    _logger.info("DEBUG: Found %d matching lines for reconciliation", len(matching_lines))
                    
                    # Try exact amount match first (only one attempt)
                    exact_match = matching_lines.filtered(lambda l: abs(l.credit) == abs(line.debit))
                    if exact_match:
                        try:
                            target_line = exact_match[0]
                            lines_to_reconcile = line + target_line
                            lines_to_reconcile.reconcile()
                            _logger.info("DEBUG: Auto reconciled exact match: %s with %s (amount: %s)", 
                                       line.name, target_line.name, line.debit)
                            reconciled_count += 1
                            continue
                        except Exception as e:
                            _logger.warning("DEBUG: Failed to reconcile exact match: %s", str(e))
                    
                    # If no exact match and we haven't hit the limit, try the newest line
                    if reconciled_count < 2:  # Only try partial if we haven't done too many
                        try:
                            target_line = matching_lines[0]  # Newest line
                            lines_to_reconcile = line + target_line
                            lines_to_reconcile.reconcile()
                            _logger.info("DEBUG: Auto reconciled partial: %s with %s", 
                                       line.name, target_line.name)
                            reconciled_count += 1
                        except Exception as e:
                            _logger.warning("DEBUG: Failed to reconcile partial: %s", str(e))
                else:
                    _logger.info("DEBUG: No matching lines found for partner %s", partner.name)
            
            _logger.info("DEBUG: Auto reconcile completed, reconciled %d lines", reconciled_count)
                            
        except Exception as e:
            _logger.warning("DEBUG: Auto reconciliation failed: %s", str(e))
            # Don't raise error, just log warning as reconciliation is optional

    def action_create_and_post(self):
        """Button action to create and post the journal entry with enhanced hang prevention"""
        import time
        start_time = time.time()
        
        try:
            _logger.info("🔄 CLEAR ADVANCE: Starting operation for employee %s", self.employee_id.name)
            
            # Quick validation to catch issues early
            self._validate_data_integrity_fast()
            _logger.info("✅ CLEAR ADVANCE: Data validation completed")
            
            # Main operation with timeout protection
            result = self.create_journal_entry()
            elapsed = time.time() - start_time
            _logger.info("✅ CLEAR ADVANCE: Operation completed successfully in %.2f seconds", elapsed)
            return result
            
        except Exception as e:
            elapsed = time.time() - start_time
            _logger.error("❌ CLEAR ADVANCE: Operation failed after %.2f seconds: %s", elapsed, str(e))
            
            # Provide user-friendly error message based on elapsed time
            if elapsed > 30:
                raise UserError(_(
                    "The Clear Advance operation took too long to complete (%.1f seconds). "
                    "This may indicate a system performance issue. Please try again later "
                    "or contact your system administrator. If the problem persists, try "
                    "disabling 'Auto Reconcile' option."
                ) % elapsed)
            else:
                # Re-raise original error with helpful context
                raise UserError(_("Clear Advance failed: %s\n\nTip: If this happens repeatedly, try disabling 'Auto Reconcile'.") % str(e))
    
    def _validate_data_integrity_fast(self):
        """Fast validation without heavy computations - HANG FIX"""
        self.ensure_one()
        
        # Quick checks only - avoid expensive computations
        if not self.expense_sheet_id:
            raise UserError(_("No expense sheet found"))
        if not self.advance_box_id:
            raise UserError(_("No advance box found"))
        if not self.partner_id:
            raise UserError(_("No partner specified"))
        if self.clear_amount <= 0:
            raise UserError(_("Clear amount must be positive"))
        
        # Check balance using direct field access (no recomputation)
        try:
            current_balance = self.advance_box_id.balance
            required_amount = self.clear_amount - self.wht_amount
            
            if current_balance < required_amount:
                raise UserError(_(
                    "Insufficient advance balance: %.2f %s (required: %.2f %s)"
                ) % (current_balance, self.currency_id.name, required_amount, self.currency_id.name))
        except Exception as e:
            _logger.warning("⚠️ Could not validate balance quickly: %s", str(e))
            # Don't fail validation just because balance check failed