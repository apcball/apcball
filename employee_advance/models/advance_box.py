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
                # Calculate balance from posted journal entries
                # ใช้ Employee Partner โดยตรงเพื่อให้ match กับ Wizard
                partner_id = False
                
                # หา Partner ที่มีชื่อเดียวกับ Employee ก่อน (ตาม logic ของ wizard)
                employee_partner = self.env['res.partner'].search([
                    ('name', '=', record.employee_id.name),
                    ('is_company', '=', False)
                ], limit=1)
                
                if employee_partner:
                    partner_id = employee_partner.id
                    _logger.info("🎯 BALANCE DEBUG: Found employee partner %s (ID: %s)", 
                               employee_partner.name, partner_id)
                else:
                    # Fallback ไปใช้ method เดิมถ้าไม่เจอ Employee Partner
                    # Method 1: Check if address_home_id exists
                    if hasattr(record.employee_id, 'address_home_id') and record.employee_id.sudo().address_home_id:
                        partner_id = record.employee_id.sudo().address_home_id.id
                    # Method 2: Get the related user's partner
                    elif record.employee_id.user_id:
                        partner_id = record.employee_id.user_id.partner_id.id
                    # Method 3: Default to employee's work address
                    elif record.employee_id.address_id:
                        partner_id = record.employee_id.address_id.id
                        
                    _logger.info("🔄 BALANCE DEBUG: Using fallback partner ID: %s", partner_id)
                
                if not partner_id:
                    _logger.warning("⚠️ BALANCE DEBUG: No partner found, setting balance to 0")
                    record.balance = 0.0
                    continue
                
                domain = [
                    ('account_id', '=', record.account_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('partner_id', '=', partner_id),
                ]
                
                _logger.info("📋 BALANCE DEBUG: Searching with domain: %s", domain)
                
                # ใช้ search แทน read_group เพื่อ debug ง่ายขึ้น
                lines = self.env['account.move.line'].search(domain)
                _logger.info("📋 BALANCE DEBUG: Found %d lines", len(lines))
                
                total_debit = sum(lines.mapped('debit'))
                total_credit = sum(lines.mapped('credit'))
                balance = total_debit - total_credit
                
                _logger.info("💰 BALANCE DEBUG: Debit: %s, Credit: %s, Balance: %s", 
                           total_debit, total_credit, balance)
                           
                for line in lines:
                    _logger.info("  📝 Line: %s | %s | Dr: %s | Cr: %s | Move: %s", 
                               line.date, line.name, line.debit, line.credit, line.move_id.name)
                
                record.balance = balance
            else:
                _logger.warning("⚠️ BALANCE DEBUG: Missing account or employee")
                record.balance = 0.0

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
    
    def _get_employee_partner(self):
        """Get the partner associated with the employee for advance transactions"""
        self.ensure_one()
        partner_id = False
        
        # Method 1: Check if address_home_id exists (from hr_contract module)
        if hasattr(self.employee_id, 'address_home_id'):
            partner_id = self.employee_id.sudo().address_home_id.id if self.employee_id.sudo().address_home_id else False
        
        # If still not found, try to get the related user's partner (which might contain private address)
        if not partner_id and self.employee_id.user_id:
            partner_id = self.employee_id.user_id.partner_id.id
        
        # If still not found, default to employee's address_id (work address)
        if not partner_id:
            partner_id = self.employee_id.address_id.id if self.employee_id.address_id else False
        
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