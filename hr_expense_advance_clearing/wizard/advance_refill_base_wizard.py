from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class AdvanceRefillBaseWizard(models.TransientModel):
    _name = 'advance.refill.base.wizard'
    _description = 'Refill Employee Advance to Base Amount'

    employee_id = fields.Many2one(
        'hr.employee',
        readonly=True,
        required=True
    )
    box_id = fields.Many2one(
        'employee.advance.box',
        readonly=True,
        required=True
    )
    journal_id = fields.Many2one(
        'account.journal',
        required=True,
        domain=[('type', 'in', ('cash', 'bank'))]
    )
    date = fields.Date(
        string="Date",
        default=fields.Date.context_today,
        required=True
    )
    current_balance = fields.Monetary(
        readonly=True,
        string="Current Balance"
    )
    base_amount_ref = fields.Monetary(
        string="Base Amount",
        help="Current remembered base amount, can be modified"
    )
    topup_amount = fields.Monetary(
        readonly=True,
        string="Top-up Amount"
    )
    currency_id = fields.Many2one(
        'res.currency',
        readonly=True
    )
    initial_base_amount = fields.Monetary(
        string="Initial Base Amount",
        help="Enter initial base amount if none exists"
    )
    need_initial_base = fields.Boolean(
        default=False,
        help="Flag to indicate if initial base amount is needed"
    )
    manual_base_amount = fields.Monetary(
        string="New Base Amount",
        help="Set new base amount (defaults to current base amount)"
    )

    @api.model
    def default_get(self, fields):
        res = super().default_get(fields)
        active_id = self.env.context.get('active_id')
        active_model = self.env.context.get('active_model')
        
        # Check if called from the button (with explicit context values)
        if self.env.context.get('default_employee_id'):
            res['employee_id'] = self.env.context.get('default_employee_id')
            res['box_id'] = self.env.context.get('default_box_id')
            res['current_balance'] = self.env.context.get('default_current_balance', 0)
            res['base_amount_ref'] = self.env.context.get('default_base_amount_ref', 0)
            res['manual_base_amount'] = self.env.context.get('default_base_amount_ref', 0)  # Default to current base
            res['currency_id'] = self.env.context.get('default_currency_id')
            res['journal_id'] = self.env.context.get('default_journal_id')
            
            # Check if we need an initial base amount
            if self.env.context.get('default_base_amount_ref', 0) == 0:
                res['need_initial_base'] = True
            else:
                base = self.env.context.get('default_base_amount_ref', 0)
                balance = self.env.context.get('default_current_balance', 0)
                res['topup_amount'] = max(base - balance, 0)
        # Fallback to active_id if called from another context
        elif active_model == 'employee.advance.box' and active_id:
            box = self.env['employee.advance.box'].browse(active_id)
            res['employee_id'] = box.employee_id.id
            res['box_id'] = box.id
            res['current_balance'] = box.balance
            res['base_amount_ref'] = box.remember_base_amount
            res['manual_base_amount'] = box.remember_base_amount  # Default to current base
            res['currency_id'] = box.currency_id.id
            
            # Check if we need an initial base amount
            if box.remember_base_amount == 0:
                res['need_initial_base'] = True
            else:
                res['topup_amount'] = max(box.remember_base_amount - box.balance, 0)
                
            # Set default journal from box if available
            if box.journal_id:
                res['journal_id'] = box.journal_id.id
        
        return res

    @api.onchange('initial_base_amount', 'current_balance', 'base_amount_ref', 'need_initial_base', 'manual_base_amount')
    def _onchange_calculate_topup(self):
        """Calculate topup amount based on base and current balance"""
        # Priority: manual_base_amount > initial_base_amount (when needed) > base_amount_ref
        if self.manual_base_amount > 0:
            # Use manual base amount if provided (highest priority)
            self.topup_amount = max(self.manual_base_amount - self.current_balance, 0)
        elif self.need_initial_base and self.initial_base_amount > 0:
            self.topup_amount = max(self.initial_base_amount - self.current_balance, 0)
        elif not self.need_initial_base:
            self.topup_amount = max(self.base_amount_ref - self.current_balance, 0)
        else:
            self.topup_amount = 0

    def action_refill(self):
        """Refill the advance box to the base amount"""
        self.ensure_one()
        
        # Validate partner exists for employee
        partner = self.box_id.employee_id.user_partner_id
        if not partner:
            raise UserError(_("Employee %s has no private address (partner).") % self.box_id.employee_id.name)

        # Validate journal has a default debit account
        if not self.journal_id.default_account_id:
            raise UserError(_("Selected journal %s has no default account.") % self.journal_id.name)

        # Check if fiscal period is locked
        if self.box_id.company_id:
            # Use the lock date check from the company
            company = self.box_id.company_id
            if company.fiscalyear_lock_date and self.date and self.date <= company.fiscalyear_lock_date:
                raise UserError(_("You cannot add/update entries prior to the lock date."))

        # Determine the base amount to use
        # Priority: manual_base_amount > initial_base_amount (when needed) > base_amount_ref
        if self.manual_base_amount > 0:
            # Use manual base amount if provided (highest priority)
            base_amount = self.manual_base_amount
        elif self.need_initial_base and self.initial_base_amount > 0:
            if self.initial_base_amount <= 0:
                raise UserError(_("Initial base amount must be greater than zero."))
            base_amount = self.initial_base_amount
        else:
            base_amount = self.base_amount_ref

        # Calculate topup amount
        topup_amount = max(base_amount - self.current_balance, 0)

        # If topup amount is zero or negative, raise warning
        if topup_amount <= 0:
            raise UserError(_("Current balance is greater than or equal to base, nothing to refill."))

        # Create journal entry
        move_vals = {
            'journal_id': self.journal_id.id,
            'date': fields.Date.context_today(self),
            'ref': f'Advance Refill - {self.box_id.employee_id.name}',
            'company_id': self.box_id.company_id.id,
            'line_ids': [
                (0, 0, {
                    'account_id': self.box_id.account_id.id,
                    'partner_id': partner.id,
                    'debit': topup_amount,
                    'credit': 0,
                    'name': f'Advance Refill for {self.box_id.employee_id.name}',
                }),
                (0, 0, {
                    'account_id': self.journal_id.default_account_id.id,
                    'debit': 0,
                    'credit': topup_amount,
                    'name': f'Advance Refill for {self.box_id.employee_id.name}',
                }),
            ]
        }

        move = self.env['account.move'].create(move_vals)
        move.action_post()  # Post the move immediately

        # Update remember_base_amount to the new base amount (not just the new balance)
        self.box_id.remember_base_amount = base_amount

        # Post a message on the advance box
        message = _(
            "Refilled to base: Base %(base)s, Previous %(balance_before)s, "
            "Top-up %(amount)s, New %(balance_after)s, Move %(move_ref)s.",
            base=self.box_id.currency_id.round(base_amount),
            balance_before=self.box_id.currency_id.round(self.current_balance),
            amount=self.box_id.currency_id.round(topup_amount),
            balance_after=self.box_id.currency_id.round(base_amount),  # New balance equals new base
            move_ref=move.name
        )
        self.box_id.message_post(body=message)

        return {'type': 'ir.actions.act_window_close'}