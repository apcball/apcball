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
    refill_ids = fields.One2many(
        'advance.box.refill',
        'box_id',
        string='Refill History',
        help='History of refills for this advance box'
    )
    refill_count = fields.Integer(
        string='Refill Count',
        compute='_compute_refill_count'
    )

    @api.depends('refill_ids')
    def _compute_refill_count(self):
        for record in self:
            record.refill_count = len(record.refill_ids)

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

    @api.depends('account_id', 'employee_id', 'journal_id')
    def _compute_balance(self):
        """
        Compute balance from journal entries.
        ALWAYS filter by employee partner to separate each employee's advance box.
        Use account_id (113001) with partner filtering for balance calculation.
        """
        for record in self:
            _logger.info("🔍 BALANCE DEBUG: Computing for advance box %s (employee: %s)", 
                       record.id, record.employee_id.name)
            
            # Get employee partner for filtering
            partner_id = record._get_employee_partner()
            
            if not partner_id:
                _logger.warning("⚠️ BALANCE DEBUG: No partner found for employee %s, setting balance to 0", 
                              record.employee_id.name)
                record.balance = 0.0
                continue
            
            # Use account_id (113001 เงินทดรองจ่าย) with partner filtering
            if record.account_id and record.employee_id:
                domain = [
                    ('account_id', '=', record.account_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('partner_id', '=', partner_id),
                ]
                
                _logger.info("📋 BALANCE DEBUG: Searching account %s (%s) with partner %s", 
                           record.account_id.code, record.account_id.name, partner_id)
                
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

    def action_view_refill_history(self):
        """Open the refill history for this advance box"""
        self.ensure_one()
        
        return {
            'name': _('Refill History'),
            'type': 'ir.actions.act_window',
            'res_model': 'advance.box.refill',
            'view_mode': 'tree,form',
            'domain': [('box_id', '=', self.id)],
            'context': {'default_box_id': self.id},
        }

    def action_refill_box_wizard(self):
        """Open wizard to refill this advance box"""
        self.ensure_one()
        
        # Create wizard with current box pre-selected
        wizard = self.env['wizard.refill.advance.box'].create({
            'box_id': self.id,
        })
        
        return {
            'name': _('Refill Advance Box'),
            'type': 'ir.actions.act_window',
            'res_model': 'wizard.refill.advance.box',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
