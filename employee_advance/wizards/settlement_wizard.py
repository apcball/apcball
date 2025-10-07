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
    amount_mode = fields.Selection([
        ('full', 'Full Settlement'),
        ('partial', 'Partial Settlement')
    ], string='Amount Mode', default='full', required=True)
    amount_to_settle = fields.Monetary(
        string='Amount to Settle',
        currency_field='currency_id'
    )
    scenario = fields.Selection([
        ('pay_employee', 'Pay Employee (Dr 141101 / Cr Bank)'),
        ('employee_refund', 'Employee Refund (Dr Bank / Cr 141101)'),
        ('write_off', 'Write-off / Reclass'),
    ], string='Settlement Scenario', required=True)
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
                default_scenario = 'pay_employee' if box.balance > 0 else 'employee_refund'
                
                # Try to set a default journal based on the advance box if available
                default_journal = box.journal_id if box.journal_id and box.journal_id.type in ('bank', 'cash') else None
                if not default_journal and default_scenario in ('pay_employee', 'employee_refund'):
                    # Find any bank or cash journal if none set on the box
                    default_journal = self.env['account.journal'].search([
                        ('company_id', '=', box.company_id.id),
                        ('type', 'in', ('bank', 'cash'))
                    ], limit=1, order="type desc, id asc")
                
                res.update({
                    'box_id': box.id,
                    'employee_id': box.employee_id.id,
                    'current_balance': box.balance,
                    'memo': f'Advance Settlement for {box.employee_id.name}',
                    'scenario': default_scenario,
                    'journal_id': default_journal.id if default_journal else False,
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
            else:
                # writeoff: bank journal not required
                w.journal_id = False

    @api.constrains('scenario', 'journal_id')
    def _check_journal_required(self):
        for w in self:
            if w.scenario in ('pay_employee', 'employee_refund') and not w.journal_id:
                raise ValidationError(_("Please select a Bank/Cash journal for this settlement scenario."))

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
        
        # Check if fiscal period is locked
        if self.settlement_date:
            company_id = self.company_id or self.env.company
            # Use the proper method to check lock date
            locked_date = company_id._get_user_fiscal_lock_date()
            if self.settlement_date <= locked_date:
                raise UserError(_("You cannot add/modify entries prior to and during the lock date %s.", locked_date))

        # Validate journal based on scenario
        if self.scenario in ('pay_employee', 'employee_refund'):
            if not self.journal_id or self.journal_id.type not in ('bank', 'cash'):
                raise ValidationError(_("Please select a bank or cash journal for this scenario."))
        elif self.scenario == 'write_off':
            # For write-off, any journal type can be used
            if not self.journal_id:
                raise ValidationError(_("Please select a journal for this write-off scenario."))
            if not self.writeoff_account_id:
                raise ValidationError(_("Write-off account is required for write-off scenario."))
        else:
            # For other scenarios, ensure journal is selected
            if not self.journal_id:
                raise ValidationError(_("Please select a journal."))

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
        
        move_vals = {
            'journal_id': self.journal_id.id,
            'move_type': 'entry',
            'date': self.settlement_date,
            'ref': self.memo or f'Advance Settlement for {self.employee_id.name}',
            'company_id': self.company_id.id,
        }
        # Ensure journal has a sequence and create if missing
        self.env['hr.expense.advance.journal.utils'].ensure_journal_sequence(self.journal_id)
        
        lines = []
        
        if self.scenario == 'pay_employee':
            # Dr 141101 (employee) Cr Bank (journal.default_account)
            lines.append((0, 0, {
                'account_id': self.box_id.account_id.id,
                'partner_id': partner_id,
                'debit': self.target_amount,
                'credit': 0.0,
                'name': f'Payment to {self.employee_id.name}',
                'company_id': self.company_id.id,
            }))
            lines.append((0, 0, {
                'account_id': self.journal_id.default_account_id.id,
                'partner_id': partner_id,
                'debit': 0.0,
                'credit': self.target_amount,
                'name': f'Payment to {self.employee_id.name}',
                'company_id': self.company_id.id,
            }))
            
        elif self.scenario == 'employee_refund':
            # Dr Bank Cr 141101 (employee)
            lines.append((0, 0, {
                'account_id': self.journal_id.default_account_id.id,
                'partner_id': partner_id,
                'debit': self.target_amount,
                'credit': 0.0,
                'name': f'Refund from {self.employee_id.name}',
                'company_id': self.company_id.id,
            }))
            lines.append((0, 0, {
                'account_id': self.box_id.account_id.id,
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

    def action_settle_advance(self):
        """Main method to settle the advance"""
        self.ensure_one()
        
        # Validate the settlement
        self._validate_settlement()
        
        # Create the settlement move
        move = self._create_settlement_move()
        
        # Post the move
        move.action_post()
        
        # Reconcile if enabled
        self._reconcile_141101_lines(move)

        # Force recompute of the advance box balance after posting/reconciliation
        try:
            self.box_id._trigger_balance_recompute()
        except Exception:
            # Don't block the user flow if recompute fails; log could be added if desired
            pass
        
        # Log in the advance box
        self.box_id.message_post(
            body=_("Advance box settled with journal entry %s. Amount: %s. Scenario: %s." % 
                  (move.name, self.target_amount, self.scenario))
        )
        
        # Create activity if requested
        if self.create_activity and self.activity_user_id and self.activity_type_id:
            self.box_id.activity_schedule(
                activity_type_id=self.activity_type_id.id,
                summary=self.activity_note or f'Advance settlement follow-up for {self.employee_id.name}',
                note=self.activity_note,
                user_id=self.activity_user_id.id
            )
        
        # Return action to view the created move
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
            'name': _('Settlement Journal Entry')
        }