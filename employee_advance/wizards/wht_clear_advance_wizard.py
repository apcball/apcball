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
        default=True,
        help="Automatically reconcile the journal entry with matching payable entries"
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
        res = super().default_get(fields_list)
        
        # Get advance box from context first (from bill action - ถูกต้องที่สุด) 
        advance_box_id = self.env.context.get('default_advance_box_id')
        if advance_box_id:
            res['advance_box_id'] = advance_box_id
            advance_box = self.env['employee.advance.box'].browse(advance_box_id)
            _logger.info("DEBUG: Using advance box from context: %s (id: %s, balance: %s)", 
                       advance_box.display_name, advance_box_id, advance_box.balance)
        
        # Get expense sheet from context
        expense_sheet_id = self.env.context.get('default_expense_sheet_id')
        if expense_sheet_id:
            expense_sheet = self.env['hr.expense.sheet'].browse(expense_sheet_id)
            if expense_sheet:
                res['expense_sheet_id'] = expense_sheet.id
                
                # Set employee info
                if expense_sheet.employee_id:
                    res['employee_id'] = expense_sheet.employee_id.id
                    
                    # Set advance box only if not already set from context
                    if not advance_box_id and expense_sheet.advance_box_id:
                        res['advance_box_id'] = expense_sheet.advance_box_id.id
                        _logger.info("DEBUG: Using advance box from expense sheet: %s (id: %s)", 
                                   expense_sheet.advance_box_id.display_name, expense_sheet.advance_box_id.id)
                    else:
                        # Fallback: ค้นหา advance box ของ employee (เดิม)
                        advance_box = self.env['employee.advance.box'].search([
                            ('employee_id', '=', expense_sheet.employee_id.id)
                        ], limit=1)
                        if advance_box:
                            res['advance_box_id'] = advance_box.id
                            _logger.info("DEBUG: Using fallback advance box: %s (id: %s)", 
                                       advance_box.display_name, advance_box.id)
        
        # Set partner info from context - FORCE VENDOR FROM BILL
        partner_id = self.env.context.get('default_partner_id')
        wht_partner_id = self.env.context.get('default_wht_partner_id')
        
        _logger.info("DEBUG: default_get context - partner_id: %s, wht_partner_id: %s", partner_id, wht_partner_id)
        
        if partner_id:
            partner = self.env['res.partner'].browse(partner_id)
            res['partner_id'] = partner_id
            _logger.info("DEBUG: Setting partner_id from context: %s (name: %s)", partner_id, partner.name)
        
        if wht_partner_id:
            wht_partner = self.env['res.partner'].browse(wht_partner_id)
            res['wht_partner_id'] = wht_partner_id
            _logger.info("DEBUG: Setting wht_partner_id from context: %s (name: %s)", wht_partner_id, wht_partner.name)
        elif partner_id:
            # Default WHT partner to same as partner
            res['wht_partner_id'] = partner_id
            _logger.info("DEBUG: Setting wht_partner_id same as partner_id: %s", partner_id)
        
        # Set amounts from context
        if self.env.context.get('default_clear_amount'):
            res['clear_amount'] = self.env.context.get('default_clear_amount')
        
        if self.env.context.get('default_amount_base'):
            res['amount_base'] = self.env.context.get('default_amount_base')
        
        return res

    @api.depends('wht_tax_id')
    def _compute_wht_tax_rate(self):
        for record in self:
            if record.wht_tax_id:
                record.wht_tax_rate = abs(record.wht_tax_id.amount)
            else:
                record.wht_tax_rate = 0.0

    @api.depends('amount_base', 'wht_tax_id')
    def _compute_wht_amount(self):
        for wizard in self:
            if wizard.wht_tax_id and wizard.amount_base:
                # WHT taxes have negative rates, so we negate to get positive WHT amount
                wizard.wht_amount = abs(wizard.amount_base * (wizard.wht_tax_id.amount / 100))
            else:
                # No WHT tax selected or no base amount
                wizard.wht_amount = 0.0
    
    @api.depends('clear_amount', 'wht_amount')
    def _compute_net_amount(self):
        for wizard in self:
            wizard.net_amount = wizard.clear_amount - wizard.wht_amount

    @api.constrains('clear_amount', 'wht_amount', 'wht_tax_id', 'amount_base')
    def _check_amounts(self):
        for record in self:
            if record.clear_amount <= 0:
                raise ValidationError(_("Clear amount must be greater than zero."))
            if record.wht_amount < 0:
                raise ValidationError(_("WHT amount cannot be negative."))
            if record.wht_amount >= record.clear_amount:
                raise ValidationError(_("WHT amount cannot be equal to or greater than clear amount."))
            
            # ถ้าเลือก WHT Tax แล้วต้องใส่ Base Amount
            if record.wht_tax_id and not record.amount_base:
                raise ValidationError(_("Base Amount is required when WHT Tax is selected."))

    @api.onchange('advance_box_id')
    def _onchange_advance_box_id(self):
        if self.advance_box_id:
            # Set default journal from advance box if available
            if self.advance_box_id.journal_id:
                # Look for a general journal, fallback to advance box journal
                general_journals = self.env['account.journal'].search([
                    ('type', '=', 'general'),
                    ('company_id', '=', self.company_id.id)
                ], limit=1)
                if general_journals:
                    self.journal_id = general_journals[0]

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
        
        # Validate advance box balance
        required_amount = self.clear_amount - self.wht_amount
        current_balance = self.advance_box_id.balance
        
        if current_balance < required_amount:
            # Refresh balance to get latest data
            self.advance_box_id.refresh_balance()
            current_balance = self.advance_box_id.balance
            
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

        # Create move lines
        move_lines = []
        
        # Dr Payable (partner) = clear_amount
        move_lines.append((0, 0, {
            'name': _('Clear advance with WHT - %s') % self.partner_id.name,
            'account_id': payable_account.id,
            'partner_id': self.partner_id.id,
            'debit': self.clear_amount,
            'credit': 0.0,
            'currency_id': self.currency_id.id,
        }))
        
        # Cr Advance Box (employee advance account) = clear_amount - wht_amount
        advance_credit = self.clear_amount - self.wht_amount
        move_lines.append((0, 0, {
            'name': _('Clear from advance box - %s') % self.employee_id.name,
            'account_id': advance_account.id,
            'partner_id': self.employee_id.user_id.partner_id.id if self.employee_id.user_id else False,
            'debit': 0.0,
            'credit': advance_credit,
            'currency_id': self.currency_id.id,
        }))
        
        # Cr WHT Payable = wht_amount (only if WHT is selected)
        if self.wht_tax_id and self.wht_amount > 0:
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
            move = self.env['account.move'].create(move_vals)
            
            # Post the journal entry
            move.action_post()
            
            # Auto reconcile with related bills/payments if enabled
            if self.auto_reconcile:
                self._auto_reconcile(move)
            
            # Link to expense sheet
            self.expense_sheet_id.write({
                'bill_ids': [(4, move.id)],
                'is_billed': True,
            })
            
            # Update advance box balance (this should trigger recomputation)
            self.advance_box_id._compute_balance()
            
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

    def _auto_reconcile(self, move):
        """Auto reconcile the journal entry with related payables"""
        self.ensure_one()
        
        try:
            # Find payable lines from the move (Dr lines with partners)
            payable_lines = move.line_ids.filtered(
                lambda l: l.debit > 0 and l.partner_id and l.account_id.account_type == 'liability_payable'
            )
            
            for line in payable_lines:
                partner = line.partner_id
                account = line.account_id
                
                # Find unreconciled payable lines for the same partner and account
                domain = [
                    ('partner_id', '=', partner.id),
                    ('account_id', '=', account.id),
                    ('reconciled', '=', False),
                    ('parent_state', '=', 'posted'),
                    ('id', '!=', line.id)  # Exclude the current line
                ]
                
                # Look for matching lines (bills, payments, etc.)
                matching_lines = self.env['account.move.line'].search(domain)
                
                # Find lines that can be reconciled (opposite balance)
                reconcilable_lines = matching_lines.filtered(
                    lambda l: (l.debit == 0 and l.credit > 0) or  # Credit lines (bills)
                             (l.credit == 0 and l.debit > 0)      # Other debit lines
                )
                
                if reconcilable_lines:
                    # Try to reconcile with exact amount match first
                    for target_line in reconcilable_lines:
                        if abs(line.debit) == abs(target_line.credit):
                            # Exact match - reconcile
                            lines_to_reconcile = line + target_line
                            try:
                                lines_to_reconcile.reconcile()
                                _logger.info("Auto reconciled: %s with %s (amount: %s)", 
                                           line.name, target_line.name, line.debit)
                                break
                            except Exception as e:
                                _logger.warning("Failed to auto reconcile %s with %s: %s", 
                                              line.name, target_line.name, str(e))
                                continue
                    
                    # If no exact match, try partial reconciliation
                    if not line.reconciled and reconcilable_lines:
                        try:
                            # Sort by date (newest first) and try to reconcile with the first available
                            sorted_lines = reconcilable_lines.sorted('date', reverse=True)
                            target_line = sorted_lines[0]
                            lines_to_reconcile = line + target_line
                            lines_to_reconcile.reconcile()
                            _logger.info("Auto reconciled (partial): %s with %s", 
                                       line.name, target_line.name)
                        except Exception as e:
                            _logger.warning("Failed to auto reconcile (partial) %s: %s", 
                                          line.name, str(e))
                            
        except Exception as e:
            _logger.warning("Auto reconciliation failed: %s", str(e))
            # Don't raise error, just log warning as reconciliation is optional

    def action_create_and_post(self):
        """Button action to create and post the journal entry"""
        return self.create_journal_entry()