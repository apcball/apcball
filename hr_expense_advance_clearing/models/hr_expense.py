
from odoo import models, fields, _, api
from odoo.exceptions import UserError, ValidationError

class HrExpense(models.Model):
    _inherit = "hr.expense"

    clear_from_advance = fields.Boolean(
        string="Clear from Advance",
        default=False,
        help="If checked, this expense will be cleared from employee advance instead of creating payable"
    )

class HrExpenseSheet(models.Model):
    _inherit = "hr.expense.sheet"

    advance_clearing_type = fields.Selection([
        ('none', 'No Advance Clearing'),
        ('partial', 'Partial Advance Clearing'),
        ('full', 'Full Advance Clearing')
    ], string="Advance Clearing Type", default='none',
       help="Type of advance clearing for this expense sheet")
       
    advance_amount = fields.Monetary(
        string="Advance Amount to Clear",
        help="Amount to clear from advance (for partial clearing)"
    )
    
    advance_box_id = fields.Many2one(
        "employee.advance.box", 
        string="Advance Box",
        domain="[('employee_id', '=', employee_id)]"
    )
    
    # Legacy fields for backward compatibility
    use_advance = fields.Boolean(
        string="Clear from Advance", 
        compute="_compute_use_advance",
        inverse="_inverse_use_advance",
        help="Clear expenses from employee advance account instead of creating payable"
    )
    advance_balance_before = fields.Monetary(
        string="Advance Balance Before",
        compute="_compute_advance_balance",
        help="Employee advance balance before this expense"
    )
    advance_balance_after = fields.Monetary(
        string="Advance Balance After",
        compute="_compute_advance_balance",
        help="Estimated advance balance after this expense"
    )
    
    @api.depends("advance_clearing_type")
    def _compute_use_advance(self):
        for sheet in self:
            sheet.use_advance = sheet.advance_clearing_type != 'none'
    
    def _inverse_use_advance(self):
        for sheet in self:
            if sheet.use_advance:
                if not sheet.advance_clearing_type or sheet.advance_clearing_type == 'none':
                    sheet.advance_clearing_type = 'full'
            else:
                sheet.advance_clearing_type = 'none'
    
    @api.depends("advance_box_id", "total_amount", "advance_clearing_type", "advance_amount")
    def _compute_advance_balance(self):
        for sheet in self:
            if sheet.advance_box_id and sheet.advance_clearing_type != 'none':
                sheet.advance_balance_before = sheet.advance_box_id.balance
                
                # Calculate amount to be cleared
                if sheet.advance_clearing_type == 'full':
                    clear_amount = sheet.total_amount
                elif sheet.advance_clearing_type == 'partial':
                    clear_amount = sheet.advance_amount or 0.0
                else:
                    clear_amount = 0.0
                    
                sheet.advance_balance_after = sheet.advance_balance_before - clear_amount
            else:
                sheet.advance_balance_before = 0.0
                sheet.advance_balance_after = 0.0

    @api.onchange("employee_id")
    def _onchange_employee_id(self):
        # Skip processing if in AUTO mode
        if self.is_auto_mode:
            return
            
        if self.employee_id and self.advance_clearing_type != 'none':
            # Auto-find or create advance box
            advance_box = self.env["employee.advance.box"].search([
                ("employee_id", "=", self.employee_id.id),
                ("active", "=", True)
            ], limit=1)
            if advance_box:
                self.advance_box_id = advance_box.id
            else:
                # Create new advance box if none exists
                try:
                    self.advance_box_id = self.env["employee.advance.box"].create_for_employee(self.employee_id.id)
                except ValidationError:
                    # If creation fails, continue without advance box
                    pass

    @api.onchange("advance_clearing_type")
    def _onchange_advance_clearing_type(self):
        # Skip processing if in AUTO mode
        if self.is_auto_mode:
            return
            
        if self.advance_clearing_type != 'none':
            # Manually trigger the advance box logic
            if self.employee_id:
                advance_box = self.env["employee.advance.box"].search([
                    ("employee_id", "=", self.employee_id.id),
                    ("active", "=", True)
                ], limit=1)
                if advance_box:
                    self.advance_box_id = advance_box.id
                else:
                    # Create new advance box if none exists
                    try:
                        self.advance_box_id = self.env["employee.advance.box"].create_for_employee(self.employee_id.id)
                    except ValidationError:
                        # If creation fails, continue without advance box
                        pass
        else:
            self.advance_box_id = False
            self.advance_amount = 0.0

    @api.onchange("use_advance")
    def _onchange_use_advance(self):
        # Skip processing if in AUTO mode
        if self.is_auto_mode:
            return
            
        if self.use_advance:
            if self.advance_clearing_type == 'none':
                self.advance_clearing_type = 'full'
            # Manually trigger the advance box logic
            if self.employee_id:
                advance_box = self.env["employee.advance.box"].search([
                    ("employee_id", "=", self.employee_id.id),
                    ("active", "=", True)
                ], limit=1)
                if advance_box:
                    self.advance_box_id = advance_box.id
                else:
                    # Create new advance box if none exists
                    try:
                        self.advance_box_id = self.env["employee.advance.box"].create_for_employee(self.employee_id.id)
                    except ValidationError:
                        # If creation fails, continue without advance box
                        pass
        else:
            self.advance_clearing_type = 'none'

    def action_sheet_move_create(self):
        """Override to handle advance clearing - create direct JE instead of going through AP"""
        # If clearing from advance, create direct journal entry
        if self.advance_clearing_type != 'none' and self.advance_box_id:
            return self._create_advance_clearing_journal_entry()
        
        # Otherwise use normal expense flow
        return super().action_sheet_move_create()

    def _create_advance_clearing_journal_entry(self):
        """Create journal entry directly for advance clearing"""
        self.ensure_one()
        
        if not self.advance_box_id:
            raise UserError(_("No advance box found for employee %s") % self.employee_id.name)
            
        # Get accounts
        advance_account = self.advance_box_id.account_id
        partner = self.employee_id.user_partner_id
        
        if not partner:
            raise UserError(_("Employee %s has no User Partner set.") % self.employee_id.name)

        # Create the journal entry
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', self.company_id.id)
        ], limit=1)
        
        if not journal:
            journal = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id)
            ], limit=1)

        move_vals = {
            'ref': self.name,
            'journal_id': journal.id,
            'date': fields.Date.context_today(self),
            'company_id': self.company_id.id,
            'line_ids': [],
        }

        # Calculate clearing amount
        if self.advance_clearing_type == 'full':
            clearing_amount = self.total_amount
        elif self.advance_clearing_type == 'partial':
            clearing_amount = self.advance_amount or 0.0
        else:
            clearing_amount = 0.0

        # Create journal entry lines according to README:
        # Dr 65xxx Expense
        # Dr 119xxx VAT Input  
        # Cr 141101 Employee Advance
        # Cr 213xxx Withholding Tax Payable (if applicable)
        
        total_debit = 0.0
        move_lines = []

        # Process each expense line
        for expense in self.expense_line_ids:
            # Calculate proper tax amounts using Odoo's tax computation
            if expense.tax_ids:
                # compute_all will return base and tax breakdown
                tax_computation = expense.tax_ids.compute_all(
                    price_unit=expense.total_amount,
                    currency=self.currency_id,
                    quantity=1,
                    is_refund=False
                )
                base_amount = tax_computation.get('total_excluded', 0.0)
                taxes_comp = tax_computation.get('taxes', [])
            else:
                base_amount = expense.total_amount
                taxes_comp = []

            # Dr Expense Account (base amount without tax)
            if base_amount and base_amount > 0:
                expense_line_vals = {
                    'name': expense.name,
                    'account_id': expense.account_id.id if expense.account_id else False,
                    'debit': round(base_amount, 2),
                    'credit': 0.0,
                    'partner_id': partner.id,
                    'expense_id': expense.id,
                }
                # Add analytic distribution if exists
                if expense.analytic_distribution:
                    expense_line_vals['analytic_distribution'] = expense.analytic_distribution
                move_lines.append((0, 0, expense_line_vals))
                total_debit += round(base_amount, 2)

            # Process tax breakdown returned by compute_all
            for tax_item in taxes_comp:
                tax_amount = round(tax_item.get('amount', 0.0), 2)
                if not tax_amount:
                    continue
                # tax_item may include an account_id (repartition account) or not
                vat_acc = False
                acct_id = tax_item.get('account_id') or tax_item.get('account')
                if acct_id:
                    vat_acc = self.env['account.account'].browse(int(acct_id))
                if not vat_acc or not vat_acc.exists():
                    # fallback to configured VAT account
                    vat_acc = self._get_vat_input_account()
                if not vat_acc or not vat_acc.exists():
                    # last resort: try to find an account by name
                    vat_acc = self.env['account.account'].search([
                        ('name', 'ilike', 'ภาษีซื้อ'),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                    if not vat_acc:
                        vat_acc = self.env['account.account'].search([
                            ('name', 'ilike', 'vat'),
                            ('company_id', '=', self.company_id.id)
                        ], limit=1)

                if vat_acc and tax_amount > 0:
                    vat_line_vals = {
                        'name': f'ภาษีซื้อ - {expense.name}',
                        'account_id': vat_acc.id,
                        'debit': tax_amount,
                        'credit': 0.0,
                        'partner_id': partner.id,
                    }
                    # Include tax_line_id if available
                    if tax_item.get('id'):
                        vat_line_vals['tax_line_id'] = int(tax_item.get('id'))
                    if expense.analytic_distribution:
                        vat_line_vals['analytic_distribution'] = expense.analytic_distribution
                    move_lines.append((0, 0, vat_line_vals))
                    total_debit += tax_amount

        # Cr Employee Advance (clearing amount = total debit)
        if total_debit > 0:
            move_lines.append((0, 0, {
                'name': f'Advance Clearing - {self.name}',
                'account_id': advance_account.id,
                'debit': 0.0,
                'credit': total_debit,
                'partner_id': partner.id,
            }))

        move_vals['line_ids'] = move_lines

        # Create and post the move
        move = self.env['account.move'].create(move_vals)
        move.action_post()

        # Update sheet state and link the move
        self.account_move_ids = [(4, move.id)]
        self.state = 'done'

        # Update advance box balance
        self.advance_box_id._compute_balance()

        # Add message
        self.message_post(
            body=_("Advance clearing journal entry created: %s (Amount: %s)") % (
                move.name, total_debit
            )
        )

        return {
            'type': 'ir.actions.act_window',
            'name': _('Journal Entry'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_vat_input_account(self):
        """Get VAT Input account from configuration"""
        params = self.env['ir.config_parameter'].sudo()
        # Prefer explicit account ID saved in system parameters
        vat_account_id = params.get_param('hr_expense_advance_clearing.vat_input_account_id', '')
        if vat_account_id:
            try:
                vat_acc = self.env['account.account'].browse(int(vat_account_id))
                if vat_acc and vat_acc.exists():
                    return vat_acc
            except (ValueError, TypeError):
                # fall through to check code param
                pass

        # Next, prefer account code parameter if provided
        vat_account_code = params.get_param('hr_expense_advance_clearing.vat_input_account_code', '')
        if vat_account_code:
            vat_acc = self.env['account.account'].search([
                ('code', '=', vat_account_code),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
            if vat_acc:
                return vat_acc

        # Fallback to search by code pattern
        return self.env['account.account'].search([
            ('code', '=like', '119%'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def _get_wht_payable_account(self):
        """Get Withholding Tax Payable account from configuration"""
        params = self.env['ir.config_parameter'].sudo()
        wht_account_id = params.get_param('hr_expense_advance_clearing.wht_payable_account_id', False)
        
        if wht_account_id:
            return self.env['account.account'].browse(int(wht_account_id))
        
        # Fallback to search by code pattern
        return self.env['account.account'].search([
            ('code', '=like', '213%'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

    def action_open_advance_box(self):
        """Open the employee's advance box"""
        self.ensure_one()
        if not self.advance_box_id:
            return {}
            
        return {
            "type": "ir.actions.act_window",
            "name": _("Advance Box"),
            "res_model": "employee.advance.box",
            "res_id": self.advance_box_id.id,
            "view_mode": "form",
            "target": "current",
        }
