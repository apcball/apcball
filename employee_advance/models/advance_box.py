from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class EmployeeAdvanceBox(models.Model):
    _name = 'employee.advance.box'
    _description = 'Employee Advance Box'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )
    employee_id = fields.Many2one(
        'hr.employee',
        string='Employee',
        required=True
    )
    account_id = fields.Many2one(
        'account.account',
        string='Account',
        required=True,
        domain="[('deprecated', '=', False), ('company_id', '=', company_id)]",
        default=lambda self: self._default_account()
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        domain=[('type', 'in', ['bank', 'cash'])],
        help='Journal for top-ups and refunds'
    )
    remember_base_amount = fields.Monetary(
        string='Base Amount',
        currency_field='currency_id',
        help='Base target amount for refill'
    )
    balance = fields.Monetary(
        string='Balance',
        compute='_compute_balance',
        currency_field='currency_id',
        store=True,
        help='Current balance in the advance box'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    # Payment tracking fields
    payment_ids = fields.One2many(
        'account.payment',
        compute='_compute_payment_ids',
        string='Related Payments',
        help='Payments related to advance box refills and settlements'
    )
    use_payment_based_refill = fields.Boolean(
        string='Use Payment-Based Refill',
        default=True,
        help='Use standard Odoo payment system for refilling advance boxes instead of direct journal entries'
    )

    @api.model
    def _default_account(self):
        # Try to find account with code 141101 or similar
        account = self.env['account.account'].search([
            ('code', '=like', '141101%'),
            ('company_id', '=', self.env.company.id)
        ], limit=1)
        return account

    @api.depends('employee_id.name')
    def _compute_name(self):
        for record in self:
            if record.employee_id:
                record.name = f"{record.employee_id.name} - Advance Box"
            else:
                record.name = "Advance Box"

    @api.depends('account_id', 'employee_id')
    def _compute_balance(self):
        for record in self:
            _logger.info("🔍 BALANCE DEBUG: Computing for advance box %s (employee: %s)",
                       record.id, record.employee_id.name)
            
            if record.account_id and record.employee_id:
                # Use the same partner resolution method as _get_employee_partner to ensure consistency
                partner_id = record._get_employee_partner()
                
                if not partner_id:
                    _logger.warning("⚠️ BALANCE DEBUG: No partner found, setting balance to 0")
                    record.balance = 0.0
                    continue
                
                # Get all journal entry lines for this advance box
                domain = [
                    ('account_id', '=', record.account_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('partner_id', '=', partner_id),
                ]
                
                _logger.info("📋 BALANCE DEBUG: Searching with domain: %s", domain)
                
                # Get journal entry lines
                lines = self.env['account.move.line'].search(domain)
                _logger.info("📋 BALANCE DEBUG: Found %d journal lines", len(lines))
                
                total_debit = sum(lines.mapped('debit'))
                total_credit = sum(lines.mapped('credit'))
                
                # Also include payment-based transactions
                payment_lines = self.env['account.move.line'].search([
                    ('account_id', '=', record.account_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('move_id.payment_ids', '!=', False),
                    ('move_id.payment_ids.advance_box_id', '=', record.id)
                ])
                
                _logger.info("💳 BALANCE DEBUG: Found %d payment lines", len(payment_lines))
                
                total_payment_debit = sum(payment_lines.mapped('debit'))
                total_payment_credit = sum(payment_lines.mapped('credit'))
                
                # Combine both journal entries and payment transactions
                combined_debit = total_debit + total_payment_debit
                combined_credit = total_credit + total_payment_credit
                balance = combined_debit - combined_credit
                
                _logger.info("💰 BALANCE DEBUG: Journal - Debit: %s, Credit: %s",
                           total_debit, total_credit)
                _logger.info("💳 BALANCE DEBUG: Payments - Debit: %s, Credit: %s",
                           total_payment_debit, total_payment_credit)
                _logger.info("💰 BALANCE DEBUG: Combined - Debit: %s, Credit: %s, Balance: %s",
                           combined_debit, combined_credit, balance)
                           
                for line in lines:
                    _logger.info("  📝 Journal Line: %s | %s | Dr: %s | Cr: %s | Move: %s",
                               line.date, line.name, line.debit, line.credit, line.move_id.name)
                
                for line in payment_lines:
                    _logger.info("  💳 Payment Line: %s | %s | Dr: %s | Cr: %s | Move: %s",
                               line.date, line.name, line.debit, line.credit, line.move_id.name)
                
                record.balance = balance
            else:
                _logger.warning("⚠️ BALANCE DEBUG: Missing account or employee")
                record.balance = 0.0

    @api.depends('account_id', 'employee_id')
    def _compute_payment_ids(self):
        """Compute related payments for this advance box"""
        for record in self:
            if record.account_id:
                # Find payments that affect this advance box account
                payments = self.env['account.payment'].search([
                    ('state', '=', 'posted'),
                    '|',
                    ('destination_account_id', '=', record.account_id.id),
                    ('move_id.line_ids.account_id', '=', record.account_id.id)
                ])
                record.payment_ids = payments
            else:
                record.payment_ids = self.env['account.payment']

    def _refresh_balance_simple(self):
        """Simple balance refresh without triggering heavy computation - HANG FIX"""
        for record in self:
            try:
                _logger.info("💰 BALANCE REFRESH: Starting for box %s", record.id)
                # Invalidate the cache to force recomputation
                record.invalidate_recordset(['balance'])
                # Force recomputation by calling the compute method directly
                record._compute_balance()
                _logger.info("💰 BALANCE REFRESH: Completed for box %s, new balance: %s", 
                           record.id, record.balance)
            except Exception as e:
                _logger.warning("⚠️ Balance refresh failed for %s: %s", record.name, str(e))
                # Don't fail the entire operation if balance refresh fails
    
    def _trigger_balance_recompute(self):
        """Method to manually recompute the balance field - HANG FIX APPLIED"""
        try:
            # Use the simple refresh method instead of heavy computation
            self._refresh_balance_simple()
            _logger.debug("💰 Balance recompute completed for %d records", len(self))
        except Exception as e:
            _logger.warning("⚠️ Balance recompute failed: %s", str(e))
            # Don't fail the entire operation if balance recompute fails

    def action_refill_to_base(self):
        """Open wizard to refill advance box to base amount"""
        self.ensure_one()
        
        # Check if we have required data
        if not self.account_id:
            raise UserError(_("Please set the advance account."))
        if not self.journal_id:
            raise UserError(_("Please set the journal for advance transactions."))
        if not self._get_employee_partner():
            raise UserError(_("Please set the employee's private address."))
        if not self.remember_base_amount:
            raise UserError(_("Please set the base amount to refill to."))
            
        # Calculate top-up amount
        current_balance = self.balance
        topup_amount = max(self.remember_base_amount - current_balance, 0)
        
        if topup_amount <= 0:
            raise UserError(_("Current balance is already at or above the base amount."))
        
        # Open refill wizard
        wizard = self.env['advance.refill.base.wizard'].create({
            'advance_box_id': self.id,
            'current_balance': current_balance,
            'base_amount_ref': self.remember_base_amount,
            'topup_amount': topup_amount,
        })
        
        return {
            'name': _('Refill to Base'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.refill.base.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    def action_refill_to_base_payment(self):
        """Open payment register for advance box refill using standard Odoo payments"""
        self.ensure_one()
        
        # Check if we have required data
        if not self.account_id:
            raise UserError(_("Please set the advance account."))
        if not self.journal_id:
            raise UserError(_("Please set the journal for advance transactions."))
        if not self._get_employee_partner():
            raise UserError(_("Please set the employee's private address."))
        if not self.remember_base_amount:
            raise UserError(_("Please set the base amount to refill to."))
            
        # Calculate top-up amount
        current_balance = self.balance
        topup_amount = max(self.remember_base_amount - current_balance, 0)
        
        if topup_amount <= 0:
            raise UserError(_("Current balance is already at or above the base amount."))
        
        # Create a dummy bill to use with payment register for internal transfer
        # This is a workaround to use payment register for internal transfers
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self._get_employee_partner(),
            'invoice_date': fields.Date.context_today(self),
            'date': fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'ref': f'Advance Box Refill - {self.name}',
            'line_ids': [
                (0, 0, {
                    'name': f'Advance Box Refill - {self.name}',
                    'account_id': self.account_id.id,
                    'price_unit': topup_amount,
                    'quantity': 1,
                })
            ]
        }
        
        temp_bill = self.env['account.move'].create(bill_vals)
        temp_bill.action_post()
        
        # Link to advance box
        temp_bill.write({
            'advance_box_id': self.id,
            'is_expense_advance_bill': True
        })
        
        # Open payment register with context for internal transfer
        return {
            'name': _('Refill Advance Box'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': [temp_bill.id],
                'default_advance_box_id': self.id,
                'default_payment_type': 'outbound',
                'default_journal_id': self.journal_id.id,
                'advance_box_refill': True,
                'internal_transfer_destination_account_id': self.account_id.id,
                'default_amount': topup_amount,
            }
        }
    
    def _get_employee_partner(self):
        """Get the partner associated with the employee for advance transactions"""
        self.ensure_one()
        partner_id = False
        
        # Method 1: Check if address_home_id exists (from hr_contract module) - Primary method
        if hasattr(self.employee_id, 'address_home_id') and self.employee_id.sudo().address_home_id:
            partner_id = self.employee_id.sudo().address_home_id.id
            _logger.info("🎯 ADVANCE BOX PARTNER: Found via address_home_id: %s", partner_id)
        
        # Method 2: Get the related user's partner (which might contain private address)
        if not partner_id and self.employee_id.user_id and self.employee_id.user_id.partner_id:
            partner_id = self.employee_id.user_id.partner_id.id
            _logger.info("🎯 ADVANCE BOX PARTNER: Found via user.partner: %s", partner_id)
        
        # Method 3: Default to employee's address_id (work address)
        if not partner_id and self.employee_id.address_id:
            partner_id = self.employee_id.address_id.id
            _logger.info("🎯 ADVANCE BOX PARTNER: Found via address_id: %s", partner_id)
        
        # If still no partner found, try to create/find partner by employee name
        if not partner_id:
            try:
                # ลองหา Partner ที่มีชื่อเดียวกับ Employee ก่อน
                employee_partner = self.env['res.partner'].search([
                    ('name', '=', self.employee_id.name),
                    ('is_company', '=', False)
                ], limit=1)
                
                if employee_partner:
                    partner_id = employee_partner.id
                    _logger.info("🎯 ADVANCE BOX PARTNER: Found existing partner %s (%s) for employee %s", 
                               partner_id, employee_partner.name, self.employee_id.name)
                else:
                    # สร้าง Partner ใหม่สำหรับ Employee
                    employee_partner = self.env['res.partner'].create({
                        'name': self.employee_id.name,
                        'is_company': False,
                        'employee': True,
                        'supplier_rank': 0,
                        'customer_rank': 0,
                    })
                    partner_id = employee_partner.id
                    _logger.info("🎯 ADVANCE BOX PARTNER: Created new partner %s (%s) for employee %s", 
                               partner_id, employee_partner.name, self.employee_id.name)
                    
            except Exception as e:
                _logger.warning("⚠️ Could not create/find employee partner by name: %s", str(e))
                # Final fallback using all methods
                try:
                    if hasattr(self.employee_id, 'address_home_id') and self.employee_id.sudo().address_home_id:
                        partner_id = self.employee_id.sudo().address_home_id.id
                    elif self.employee_id.user_id:
                        partner_id = self.employee_id.user_id.partner_id.id
                    elif self.employee_id.address_id:
                        partner_id = self.employee_id.address_id.id
                    _logger.info("🔄 ADVANCE BOX PARTNER: Using fallback partner %s", partner_id)
                except Exception as e2:
                    _logger.warning("⚠️ All fallbacks failed: %s", str(e2))
        
        return partner_id

    def action_open_settlement_wizard(self):
        """Open the settlement wizard for this advance box"""
        self.ensure_one()
        
        # Create a wizard record with the current advance box
        wizard = self.env['advance.settlement.wizard'].create({
            'box_id': self.id,
        })
        
        return {
            'name': _('Settle Advance'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.settlement.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_box_id': self.id,
                'default_employee_name': self.employee_id.name,
            }
        }