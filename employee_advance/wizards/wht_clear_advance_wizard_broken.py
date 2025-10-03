from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class WhtClearAdvanceWizard(models.TransientModel):
    _n    @api.constrains('clear_amount', 'wht_amount', 'wht_tax_id', 'amount_base')
    def _check_amounts(self):
        for record in self:
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
            }))cord.clear_amount <= 0:
                raise ValidationError(_("Clear amount must be greater than zero."))
            if record.wht_amount < 0:
                raise ValidationError(_("WHT amount cannot be negative."))
            if record.wht_amount >= record.clear_amount:
                raise ValidationError(_("WHT amount cannot be equal to or greater than clear amount."))
            
            # ถ้าเลือก WHT Tax แล้วต้องใส่ Base Amount
            if record.wht_tax_id and not record.amount_base:
                raise ValidationError(_("Base Amount is required when WHT Tax is selected."))
            
            # ถ้าไม่เลือก WHT Tax ก็ไม่ต้องใส่ Base Amount
            if not record.wht_tax_id and record.amount_base:
                record.amount_base = 0.0


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
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        readonly=True,
        default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        readonly=True,
        related='company_id.currency_id'
    )
    
    # User input fields
    partner_id = fields.Many2one(
        'res.partner',
        string='Partner (Employee)',
        required=True,
        help="Employee partner for AP clearing entry"
    )
    wht_partner_id = fields.Many2one(
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
    wht_tax_id = fields.Many2one(
        'account.tax',
        string='WHT Tax',
        required=False,
        domain="[('type_tax_use', 'in', ['purchase', 'none']), ('amount', '<', 0)]",
        help="Withholding tax to apply (optional - leave blank for no WHT)"
    )
    amount_base = fields.Monetary(
        string='Base Amount',
        currency_field='currency_id',
        required=True,
        help="Base amount for WHT calculation"
    )
    wht_amount = fields.Monetary(
        string='WHT Amount',
        currency_field='currency_id',
        readonly=True,
        compute='_compute_wht_amount',
        help="Computed WHT amount (base × tax rate)"
    )
    clear_amount = fields.Monetary(
        string='Clear Amount',
        currency_field='currency_id',
        required=True,
        help="Amount to clear from Advance Box before WHT"
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain=[('type', '=', 'general')],
        help="General/Miscellaneous journal for the entry"
    )
    date = fields.Date(
        string='Date',
        default=fields.Date.context_today,
        help="Journal entry date"
    )
    ref = fields.Char(
        string='Reference',
        help="Optional reference for the journal entry"
    )
    
    # Display fields
    wht_tax_rate = fields.Float(
        string='WHT Tax Rate (%)',
        compute='_compute_wht_tax_rate',
        readonly=True
    )

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

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        
        # Get default values from context (sent from bill)
        if self.env.context.get('default_partner_id'):
            res['partner_id'] = self.env.context.get('default_partner_id')
        
        if self.env.context.get('default_wht_partner_id'):
            res['wht_partner_id'] = self.env.context.get('default_wht_partner_id')
        
        # Get expense sheet from context
        expense_sheet_id = self.env.context.get('default_expense_sheet_id')
        if expense_sheet_id:
            expense_sheet = self.env['hr.expense.sheet'].browse(expense_sheet_id)
            if expense_sheet:
                res['expense_sheet_id'] = expense_sheet.id
                
                # Only set partner_id from employee if not already set from context
                if not res.get('partner_id'):
                    employee_partner = False
                    if expense_sheet.employee_id.user_id and expense_sheet.employee_id.user_id.partner_id:
                        employee_partner = expense_sheet.employee_id.user_id.partner_id
                    elif expense_sheet.employee_id.address_home_id:
                        employee_partner = expense_sheet.employee_id.address_home_id
                    
                    if employee_partner:
                        res['partner_id'] = employee_partner.id
        
        return res

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
        if self.employee_id:
            # Set employee as default partner
            if self.employee_id.user_id and self.employee_id.user_id.partner_id:
                self.partner_id = self.employee_id.user_id.partner_id
            elif self.employee_id.address_home_id:
                self.partner_id = self.employee_id.address_home_id

    @api.constrains('clear_amount', 'wht_amount')
    def _check_amounts(self):
        for record in self:
            if record.clear_amount <= 0:
                raise ValidationError(_("Clear amount must be greater than zero."))
            if record.wht_amount < 0:
                raise ValidationError(_("WHT amount cannot be negative."))
            if record.wht_amount >= record.clear_amount:
                raise ValidationError(_("WHT amount must be less than clear amount."))

    @api.constrains('amount_base')
    def _check_base_amount(self):
        for record in self:
            if record.amount_base <= 0:
                raise ValidationError(_("Base amount must be greater than zero."))

    def _get_advance_account(self):
        """Get the advance account from advance box"""
        if not self.advance_box_id or not self.advance_box_id.account_id:
            raise UserError(_("No advance account configured for the advance box."))
        return self.advance_box_id.account_id

    def _get_partner_payable_account(self):
        """Get the payable account for the partner"""
        if not self.partner_id:
            raise UserError(_("Partner is required."))
        
        account = self.partner_id.property_account_payable_id
        if not account:
            # Fallback to company default payable account
            account = self.env['account.account'].search([
                ('account_type', '=', 'liability_payable'),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if not account:
                raise UserError(_("No payable account found for partner %s") % self.partner_id.name)
        return account

    def _get_wht_payable_account(self):
        """Get WHT payable account from tax configuration"""
        if not self.wht_tax_id:
            raise UserError(_("WHT tax is required."))
        
        # Try to get account from tax configuration
        if self.wht_tax_id.invoice_repartition_line_ids:
            for repartition_line in self.wht_tax_id.invoice_repartition_line_ids:
                if repartition_line.account_id and repartition_line.repartition_type == 'tax':
                    return repartition_line.account_id
        
        # Fallback: look for WHT payable account in chart of accounts
        wht_account = self.env['account.account'].search([
            ('code', 'ilike', '2109%'),  # Common WHT payable account code
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not wht_account:
            # Final fallback: create or use a generic WHT payable account
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
        
        # Cr WHT Payable = wht_amount (ใช้ wht_partner_id เพื่อออก PND ให้ vendor)
        if self.wht_amount > 0:
            move_lines.append((0, 0, {
                'name': _('%(tax_name)s - %(vendor_name)s') % {
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