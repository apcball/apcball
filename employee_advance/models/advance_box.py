from odoo import api, fields, models, _
from odoo.exceptions import UserError


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
            if record.account_id and record.employee_id:
                # Calculate balance from posted journal entries
                # We need to find the partner associated with the employee
                # The employee may be linked to a user who has the private address
                partner_id = False
                
                # Method 1: Check if address_home_id exists (from hr_contract module)
                if hasattr(record.employee_id, 'address_home_id'):
                    partner_id = record.employee_id.sudo().address_home_id.id if record.employee_id.sudo().address_home_id else False
                
                # If still not found, try to get the related user's partner (which might contain private address)
                if not partner_id and record.employee_id.user_id:
                    partner_id = record.employee_id.user_id.partner_id.id
                
                # If still not found, default to employee's address_id (work address)
                if not partner_id:
                    partner_id = record.employee_id.address_id.id if record.employee_id.address_id else False
                
                if not partner_id:
                    record.balance = 0.0
                    continue
                
                domain = [
                    ('account_id', '=', record.account_id.id),
                    ('move_id.state', '=', 'posted'),
                    ('partner_id', '=', partner_id),
                ]
                lines = self.env['account.move.line'].search(domain)
                
                # Calculate balance: debit - credit
                total_debit = sum(lines.mapped('debit'))
                total_credit = sum(lines.mapped('credit'))
                record.balance = total_debit - total_credit
            else:
                record.balance = 0.0

    def _trigger_balance_recompute(self):
        """Method to manually recompute the balance field"""
        # This forces a recalculation of the stored computed field
        self._compute_balance()
        # Write the values to the database to ensure they're stored
        for record in self:
            record.write({'balance': record.balance})

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