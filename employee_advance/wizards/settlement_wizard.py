from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class AdvanceSettlementWizard(models.TransientModel):
    _name = 'advance.settlement.wizard'
    _description = 'Advance Settlement Wizard'

    # Main fields
    box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        required=True,
        readonly=True,
        ondelete='cascade'
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        related='box_id.employee_id',
        readonly=True
    )
    
    # Computed current balance
    current_balance = fields.Monetary(
        string='Current Balance',
        compute='_compute_current_balance',
        currency_field='currency_id',
        help='Current balance in the advance box: >0 = company owes employee; <0 = employee owes company'
    )
    
    # Parameters
    settlement_date = fields.Date(
        string='Settlement Date',
        default=fields.Date.context_today,
        required=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain="[('company_id', '=', company_id)]"
    )
    payment_account_id = fields.Many2one(
        'account.account',
        string='Payment Account (Cash/Bank)',
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        help='Select which cash/bank account to use for the payment. Will default to journal default account if not specified.'
    )
    amount_mode = fields.Selection([
        ('full', 'Full Settlement'),
        ('partial', 'Partial Settlement')
    ], string='Amount Mode', default='full', required=True)
    amount_to_settle = fields.Monetary(
        string='Amount to Settle',
        currency_field='currency_id'
    )
    scenario = fields.Selection([
        ('pay_employee', 'Pay Employee (Dr Bank / Cr 141101) - Clear positive balance'),
        ('employee_refund', 'Employee Refund (Dr 141101 / Cr Bank) - Clear negative balance'),
        ('write_off', 'Write-off / Reclass'),
    ], string='Settlement Scenario', required=True, readonly=True,
        help="Auto-selected based on balance: Pay Employee when company owes employee (positive), Employee Refund when employee owes company (negative)")
    writeoff_policy = fields.Selection([
        ('none', 'No Write-off'),
        ('expense', 'Expense'),
        ('other_income', 'Other Income')
    ], string='Write-off Policy', default='none')
    writeoff_account_id = fields.Many2one(
        'account.account',
        string='Write-off Account',
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]"
    )
    memo = fields.Char(
        string='Memo',
        default=lambda self: 'Advance Settlement for %s' % (self.env.context.get('default_employee_name', 'Employee'))
    )
    auto_reconcile = fields.Boolean(
        string='Auto Reconcile',
        default=True
    )
    create_activity = fields.Boolean(string='Create Activity')
    activity_user_id = fields.Many2one('res.users', string='Responsible User')
    activity_type_id = fields.Many2one('mail.activity.type', string='Activity Type')
    activity_note = fields.Text(string='Activity Note')
    
    # Computed fields
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        related='box_id.currency_id',
        readonly=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        related='box_id.company_id',
        readonly=True
    )
    
    target_amount = fields.Monetary(
        string='Target Amount',
        compute='_compute_target_amount',
        currency_field='currency_id'
    )
    direction = fields.Selection([
        ('positive', 'Company owes employee'),
        ('negative', 'Employee owes company')
    ], string='Direction', compute='_compute_direction')

    @api.model
    def default_get(self, fields):
        """Set default values based on the advance box"""
        res = super().default_get(fields)
        
        if self.env.context.get('default_box_id'):
            box = self.env['employee.advance.box'].browse(self.env.context['default_box_id'])
            if box:
                # Determine the default scenario based on balance
                # Positive balance = company owes employee (pay employee)
                # Negative balance = employee owes company (employee refund)
                # Zero balance = default to write-off
                if box.balance > 0:
                    default_scenario = 'pay_employee'
                elif box.balance < 0:
                    default_scenario = 'employee_refund'
                else:
                    default_scenario = 'write_off'
                
                # Try to set a default journal based on the advance box if available
                default_journal = box.journal_id if box.journal_id and box.journal_id.type in ('bank', 'cash') else None
                if not default_journal and default_scenario in ('pay_employee', 'employee_refund'):
                    # Find any bank or cash journal if none set on the box
                    default_journal = self.env['account.journal'].search([
                        ('company_id', '=', box.company_id.id),
                        ('type', 'in', ('bank', 'cash'))
                    ], limit=1, order="type desc, id asc")
                
                # Set payment account from journal's default account
                payment_account = default_journal.default_account_id if default_journal and default_journal.default_account_id else None
                
                res.update({
                    'box_id': box.id,
                    'employee_id': box.employee_id.id,
                    'current_balance': box.balance,
                    'memo': f'Advance Settlement for {box.employee_id.name}',
                    'scenario': default_scenario,
                    'journal_id': default_journal.id if default_journal else False,
                    'payment_account_id': payment_account.id if payment_account else False,
                    'company_id': box.company_id.id
                })
        
        # Ensure scenario has a default value if not set
        if 'scenario' not in res:
            res['scenario'] = 'pay_employee'
        
        # If scenario requires a journal but none is set, try to set one
        if 'scenario' in res and 'journal_id' not in res and res['scenario'] in ('pay_employee', 'employee_refund'):
            # Get company from context or use current user's company
            company_id = self.env.context.get('force_company', self.env.company.id)
            default_journal = self.env['account.journal'].search([
                ('company_id', '=', company_id),
                ('type', 'in', ('bank', 'cash'))
            ], limit=1, order="type desc, id asc")
            if default_journal:
                res['journal_id'] = default_journal.id
                # Also set payment account
                if default_journal.default_account_id:
                    res['payment_account_id'] = default_journal.default_account_id.id
        
        return res

    @api.depends('box_id')
    def _compute_current_balance(self):
        """Compute the current balance from the advance box"""
        for record in self:
            if record.box_id:
                record.current_balance = record.box_id.balance
            else:
                record.current_balance = 0.0

    @api.depends('amount_mode', 'amount_to_settle', 'current_balance')
    def _compute_target_amount(self):
        """Compute the target amount based on settlement mode"""
        for record in self:
            if record.amount_mode == 'partial' and record.amount_to_settle:
                record.target_amount = abs(record.amount_to_settle)
            else:
                record.target_amount = abs(record.current_balance) if record.current_balance else 0.0

    @api.depends('current_balance')
    def _compute_direction(self):
        """Compute the direction of the balance"""
        for record in self:
            if record.current_balance > 0:
                record.direction = 'positive'  # Company owes employee
            elif record.current_balance < 0:
                record.direction = 'negative'  # Employee owes company
            else:
                record.direction = False

    @api.onchange('box_id')
    def _onchange_box(self):
        """Update defaults based on selected box"""
        if self.box_id:
            self.current_balance = self.box_id.balance
            self.memo = f'Advance Settlement for {self.box_id.employee_id.name}'
            # Set default scenario based on balance direction
            if self.box_id.balance > 0:
                self.scenario = 'pay_employee'
            elif self.box_id.balance < 0:
                self.scenario = 'employee_refund'
            else:
                self.scenario = 'write_off'
    
    @api.onchange('box_id', 'scenario')
    def _onchange_default_journal(self):
        """Auto-pick a sensible journal for scenarios that touch Bank/Cash."""
        for w in self:
            if w.scenario in ('pay_employee', 'employee_refund'):
                # 1) use box.journal_id if set
                journal = w.box_id.journal_id
                # 2) else fallback to company main bank journal
                if not journal:
                    journal = self.env['account.journal'].search([
                        ('type', 'in', ('bank','cash')),
                        ('company_id', '=', w.box_id.company_id.id or self.env.company.id)
                    ], limit=1, order="type desc, id asc")
                w.journal_id = journal or False
                # Auto-fill payment account from journal
                if journal and journal.default_account_id:
                    w.payment_account_id = journal.default_account_id
            else:
                # writeoff: bank journal not required
                w.journal_id = False
                w.payment_account_id = False
    
    @api.onchange('journal_id')
    def _onchange_journal_id(self):
        """Update payment account when journal changes"""
        if self.journal_id and self.journal_id.default_account_id:
            self.payment_account_id = self.journal_id.default_account_id

    @api.constrains('scenario', 'journal_id', 'payment_account_id')
    def _check_journal_required(self):
        for w in self:
            if w.scenario in ('pay_employee', 'employee_refund'):
                if not w.journal_id:
                    raise ValidationError(_("Please select a Bank/Cash journal for this settlement scenario."))
                if not w.payment_account_id:
                    raise ValidationError(_("Please select a payment account (Cash/Bank) for this settlement scenario."))
            if w.scenario == 'write_off' and w.writeoff_policy != 'none' and not w.writeoff_account_id:
                raise ValidationError(_("Please select a write-off account when using write-off policy."))

    @api.onchange('amount_mode')
    def _onchange_amount_mode(self):
        """Reset amount_to_settle when switching to full mode"""
        if self.amount_mode == 'full':
            self.amount_to_settle = 0.0

    @api.onchange('writeoff_policy')
    def _onchange_writeoff_policy(self):
        """Clear writeoff account when policy is none"""
        if self.writeoff_policy == 'none':
            self.writeoff_account_id = False

    @api.onchange('scenario')
    def _onchange_scenario(self):
        """Adjust journal domain based on scenario"""
        # The journal domain is already set for bank/cash journals
        # which is appropriate for scenarios A and B
        if self.scenario == 'write_off':
            # For write-off scenario, allow more general journals
            pass

    @api.constrains('amount_to_settle')
    def _check_amount_to_settle(self):
        """Validate amount_to_settle"""
        for record in self:
            if record.amount_mode == 'partial' and record.amount_to_settle <= 0:
                raise ValidationError(_("Partial settlement amount must be greater than 0."))

    @api.constrains('writeoff_account_id', 'writeoff_policy')
    def _check_writeoff_account(self):
        """Validate write-off account"""
        for record in self:
            if record.writeoff_policy in ('expense', 'other_income') and not record.writeoff_account_id:
                raise ValidationError(_("Write-off account is required when write-off policy is set."))

    def _validate_settlement(self):
        """Validate settlement parameters before posting"""
        self.ensure_one()
        
        # Check if balance is zero (nothing to settle)
        if abs(self.current_balance) < 0.01:
            raise UserError(_("Cannot settle advance box with zero balance."))
        
        # Check if fiscal period is locked
        if self.settlement_date:
            company_id = self.company_id or self.env.company
            # Use the proper method to check lock date
            try:
                locked_date = company_id._get_user_fiscal_lock_date()
                if locked_date and self.settlement_date <= locked_date:
                    raise UserError(_("You cannot add/modify entries prior to and during the lock date %s.", locked_date))
            except AttributeError:
                # Fallback if method doesn't exist
                if hasattr(company_id, 'fiscalyear_lock_date') and company_id.fiscalyear_lock_date:
                    if self.settlement_date <= company_id.fiscalyear_lock_date:
                        raise UserError(_("You cannot add/modify entries prior to the fiscal year lock date %s.", company_id.fiscalyear_lock_date))

        # Validate scenario matches balance direction (allow write-off for any balance)
        if self.scenario == 'pay_employee' and self.current_balance < 0:
            raise ValidationError(_("Pay Employee scenario can only be used when the company owes money to the employee (positive balance). Current balance is negative, use Employee Refund instead."))
        if self.scenario == 'employee_refund' and self.current_balance > 0:
            raise ValidationError(_("Employee Refund scenario can only be used when the employee owes money to the company (negative balance). Current balance is positive, use Pay Employee instead."))
        
        # Validate journal based on scenario
        if self.scenario in ('pay_employee', 'employee_refund'):
            if not self.journal_id or self.journal_id.type not in ('bank', 'cash'):
                raise ValidationError(_("Please select a bank or cash journal for this scenario."))
            # Check if payment account is selected
            if not self.payment_account_id:
                raise ValidationError(_("Please select a payment account (Cash/Bank) for this scenario."))
        elif self.scenario == 'write_off':
            # For write-off, ensure we have write-off account
            if self.writeoff_policy == 'none':
                raise ValidationError(_("Please select a write-off policy for write-off scenario."))
            if not self.writeoff_account_id:
                raise ValidationError(_("Write-off account is required for write-off scenario."))

        # Validate partial amount
        if self.amount_mode == 'partial' and self.amount_to_settle <= 0:
            raise ValidationError(_("Amount to settle must be greater than zero for partial settlement."))

        # Check if employee has a partner configured
        partner = self.box_id._get_employee_partner()
        if not partner:
            raise ValidationError(_("Employee does not have a private partner configured."))

        # Check if advance box has account 141101
        if not self.box_id.account_id:
            raise ValidationError(_("Advance box does not have an account configured."))

    def _create_settlement_move(self):
        """Create the settlement journal entry"""
        self.ensure_one()
        
        partner_id = self.box_id._get_employee_partner()
        if not partner_id:
            # If we still don't have a partner, try to create/find partner by employee name
            try:
                employee = self.box_id.employee_id
                if employee:
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
                _logger.warning("⚠️ Could not create/find employee partner: %s", str(e))
                # Final fallback using all methods
                try:
                    employee = self.box_id.employee_id
                    if hasattr(employee, 'address_home_id') and employee.sudo().address_home_id:
                        partner_id = employee.sudo().address_home_id.id
                    elif employee.user_id:
                        partner_id = employee.user_id.partner_id.id
                    elif employee.address_id:
                        partner_id = employee.address_id.id
                except Exception as e2:
                    _logger.warning("⚠️ Final fallback also failed: %s", str(e2))
                    raise ValidationError(_("Cannot find or create employee partner for advance settlement."))
        
        # Determine which journal to use based on scenario
        journal_to_use = self.journal_id if self.scenario != 'write_off' else self._get_default_general_journal()
        
        move_vals = {
            'journal_id': journal_to_use.id,
            'move_type': 'entry',
            'date': self.settlement_date,
            'ref': self.memo or f'Advance Settlement for {self.employee_id.name}',
            'partner_id': partner_id,  # Add partner_id for etax_transaction
            'company_id': self.company_id.id,
        }
        
        # Ensure journal has a sequence and create if missing
        try:
            self.env['hr.expense.advance.journal.utils'].ensure_journal_sequence(journal_to_use)
        except Exception as e:
            _logger.warning("Could not ensure journal sequence: %s", str(e))
            # Continue anyway as Odoo will create sequence automatically if needed
        
        lines = []
        
        if self.scenario == 'pay_employee':
            # Pay Employee: Company owes employee (balance > 0)
            # To reduce balance, need to CREDIT 141101
            # Dr Bank (increase expense/clear) Cr 141101 (reduce advance balance)
            lines.append((0, 0, {
                'account_id': self.payment_account_id.id,
                'partner_id': partner_id,
                'debit': self.target_amount,
                'credit': 0.0,
                'name': f'Settlement Payment to {self.employee_id.name}',
                'company_id': self.company_id.id,
            }))
            lines.append((0, 0, {
                'account_id': self.box_id.account_id.id,
                'partner_id': partner_id,
                'debit': 0.0,
                'credit': self.target_amount,
                'name': f'Settlement Payment to {self.employee_id.name}',
                'company_id': self.company_id.id,
            }))
            
        elif self.scenario == 'employee_refund':
            # Employee Refund: Employee owes company (balance < 0)
            # To reduce negative balance, need to DEBIT 141101
            # Dr 141101 (reduce negative balance) Cr Bank (employee pays back)
            lines.append((0, 0, {
                'account_id': self.box_id.account_id.id,
                'partner_id': partner_id,
                'debit': self.target_amount,
                'credit': 0.0,
                'name': f'Refund from {self.employee_id.name}',
                'company_id': self.company_id.id,
            }))
            lines.append((0, 0, {
                'account_id': self.payment_account_id.id,
                'partner_id': partner_id,
                'debit': 0.0,
                'credit': self.target_amount,
                'name': f'Refund from {self.employee_id.name}',
                'company_id': self.company_id.id,
            }))
            
        elif self.scenario == 'write_off':
            # Write-off to expense or other income
            if self.writeoff_policy == 'expense':
                # Dr Expense/Write-off Cr 141101
                lines.append((0, 0, {
                    'account_id': self.writeoff_account_id.id,
                    'partner_id': partner_id,
                    'debit': self.target_amount,
                    'credit': 0.0,
                    'name': f'Write-off to Expense for {self.employee_id.name}',
                    'company_id': self.company_id.id,
                }))
                lines.append((0, 0, {
                    'account_id': self.box_id.account_id.id,
                    'partner_id': partner_id,
                    'debit': 0.0,
                    'credit': self.target_amount,
                    'name': f'Write-off to Expense for {self.employee_id.name}',
                    'company_id': self.company_id.id,
                }))
            elif self.writeoff_policy == 'other_income':
                # Dr 141101 Cr Other Income
                lines.append((0, 0, {
                    'account_id': self.box_id.account_id.id,
                    'partner_id': partner_id,
                    'debit': 0.0,
                    'credit': self.target_amount,
                    'name': f'Write-off to Other Income for {self.employee_id.name}',
                    'company_id': self.company_id.id,
                }))
                lines.append((0, 0, {
                    'account_id': self.writeoff_account_id.id,
                    'partner_id': partner_id,
                    'debit': self.target_amount,
                    'credit': 0.0,
                    'name': f'Write-off to Other Income for {self.employee_id.name}',
                    'company_id': self.company_id.id,
                }))

        move_vals['line_ids'] = lines
        move = self.env['account.move'].create(move_vals)
        return move

    def _reconcile_141101_lines(self, move):
        """Reconcile new 141101 lines with existing open 141101 lines for the employee"""
        if not self.auto_reconcile:
            return

        partner_id = self.box_id._get_employee_partner()
        
        # Find all account.move.line records with the same account and partner
        all_141101_lines = self.env['account.move.line'].search([
            ('account_id', '=', self.box_id.account_id.id),
            ('partner_id', '=', partner_id),
            ('reconciled', '=', False),
            ('move_id.state', '=', 'posted')
        ])
        
        # Separate lines by debit/credit
        debit_lines = all_141101_lines.filtered(lambda l: l.debit > 0)
        credit_lines = all_141101_lines.filtered(lambda l: l.credit > 0)
        
        # Try to reconcile lines
        for debit_line in debit_lines:
            for credit_line in credit_lines:
                if debit_line.currency_id == credit_line.currency_id:
                    # Check if we can reconcile these lines
                    if debit_line.amount_residual != 0 and credit_line.amount_residual != 0:
                        try:
                            (debit_line + credit_line).reconcile()
                            break  # Move to next debit line after successful reconciliation
                        except Exception:
                            continue  # Try next credit line if reconciliation fails

    def _get_default_general_journal(self):
        """Get default general journal for write-off entries"""
        general_journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id)
        ], limit=1, order="id asc")
        if not general_journal:
            raise UserError(_("No general journal found for write-off entries. Please create one first."))
        return general_journal
    
    def action_settle_advance(self):
        """Main method to settle the advance"""
        self.ensure_one()
        
        # Validate the settlement
        self._validate_settlement()
        
        # Log the settlement attempt
        _logger.info("🏦 SETTLEMENT: Starting settlement for advance box %s (employee: %s)", 
                    self.box_id.id, self.employee_id.name)
        _logger.info("🏦 SETTLEMENT: Scenario: %s, Amount: %s, Date: %s", 
                    self.scenario, self.target_amount, self.settlement_date)
        
        try:
            # Create the settlement move
            move = self._create_settlement_move()
            
            _logger.info("🏦 SETTLEMENT: Created journal entry %s", move.name)
            
            # Post the move
            move.action_post()
            
            _logger.info("🏦 SETTLEMENT: Posted journal entry %s", move.name)
        
            # Reconcile if enabled
            if self.auto_reconcile:
                _logger.info("🏦 SETTLEMENT: Attempting auto-reconciliation")
                self._reconcile_141101_lines(move)
            
            # Force recompute of the advance box balance after posting/reconciliation
            try:
                self.box_id._trigger_balance_recompute()
                _logger.info("🏦 SETTLEMENT: Balance recomputed. New balance: %s", self.box_id.balance)
            except Exception as e:
                _logger.warning("⚠️ Balance recompute failed: %s", str(e))
            
            # Build detailed settlement message
            scenario_desc = dict(self._fields['scenario'].selection).get(self.scenario)
            settlement_msg = _("<b>Advance Settlement Completed</b><br/>") + \
                           _("<b>Journal Entry:</b> %s<br/>") % move.name + \
                           _("<b>Scenario:</b> %s<br/>") % scenario_desc + \
                           _("<b>Amount:</b> %s %s<br/>") % (self.target_amount, self.currency_id.name) + \
                           _("<b>Date:</b> %s<br/>") % self.settlement_date + \
                           _("<b>Previous Balance:</b> %s<br/>") % self.current_balance + \
                           _("<b>New Balance:</b> %s") % self.box_id.balance
            
            # Log in the advance box with detailed info
            self.box_id.message_post(
                body=settlement_msg,
                subject=_("Advance Settlement - %s") % move.name
            )
            
            # Create activity if requested
            if self.create_activity and self.activity_user_id and self.activity_type_id:
                _logger.info("🏦 SETTLEMENT: Creating follow-up activity")
                self.box_id.activity_schedule(
                    activity_type_id=self.activity_type_id.id,
                    summary=self.activity_note or f'Advance settlement follow-up for {self.employee_id.name}',
                    note=self.activity_note,
                    user_id=self.activity_user_id.id
                )
            
            _logger.info("✅ SETTLEMENT: Successfully completed settlement for advance box %s", self.box_id.id)
            
            # Return action to view the created move
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': move.id,
                'view_mode': 'form',
                'target': 'current',
                'name': _('Settlement Journal Entry')
            }
            
        except Exception as e:
            _logger.error("❌ SETTLEMENT: Failed to settle advance box %s: %s", self.box_id.id, str(e))
            raise UserError(_("Settlement failed: %s") % str(e))