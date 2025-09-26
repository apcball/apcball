from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Metadata to support advance clearing and manual linking
    expense_sheet_id = fields.Many2one('hr.expense.sheet', string='Expense Sheet', copy=False)
    advance_box_id = fields.Many2one('employee.advance.box', string='Advance Box', copy=False)
    is_expense_advance_bill = fields.Boolean(string='Is Expense Advance Bill', default=False, copy=False)

    def action_clear_advance_from_bill(self):
        """Method to be called from vendor bill to clear advance - opens Register Payment wizard"""
        self.ensure_one()
        
        # If the bill already has explicit metadata set, prefer it
        ExpenseSheet = self.env['hr.expense.sheet']
        expense_sheet = self.expense_sheet_id or ExpenseSheet.search([('bill_id', '=', self.id)], limit=1)

        # If the bill was explicitly flagged as an expense advance bill, allow proceed even if no sheet linked
        is_flagged = self.is_expense_advance_bill or self.env.context.get('force_clear_with_advance')

        # Fallback 1: try to find expense sheet by invoice_origin
        if not expense_sheet and self.invoice_origin:
            expense_sheet = ExpenseSheet.search([('name', '=', self.invoice_origin)], limit=1)

        # Fallback 2: try to parse the reference field set when creating the bill
        # The module sets ref = 'Expense Sheet {sheet.name}' when creating bills from sheets.
        if not expense_sheet and self.ref:
            try:
                if 'Expense Sheet' in self.ref:
                    # Extract the part after 'Expense Sheet' and strip whitespace
                    sheet_name = self.ref.split('Expense Sheet', 1).pop().strip()
                    # If the ref included other characters like ':' or '-', clean them
                    sheet_name = sheet_name.lstrip(':').strip()
                    if sheet_name:
                        expense_sheet = ExpenseSheet.search([('name', 'ilike', sheet_name)], limit=1)
            except Exception:
                _logger.debug('Failed to parse expense sheet name from bill ref: %s', self.ref)

        # If still not found, but the bill is flagged or context allows, try to detect employee via partner and advance box\n        if not expense_sheet:\n            if not is_flagged:\n                # Try to detect employee from partner using multiple methods\n                employee = self._find_employee_from_partner()\n                if employee:\n                    # Find advance box for the employee\n                    adv_box = self.env['employee.advance.box'].search([('employee_id', '=', employee.id)], limit=1)\n                    if adv_box:\n                        # allow proceed: create a minimal sheet placeholder? prefer to just set the advance box on bill\n                        _logger.info('Detected employee %s from partner %s and found advance box %s for bill %s', employee.name, self.partner_id.name, adv_box.name, self.name)\n                        self.sudo().write({'advance_box_id': adv_box.id})\n                        # Open register payment wizard instead of creating JE directly\n                        return self._open_register_payment_wizard(adv_box)\n\n                # No detection - raise\n                error_msg = _(\n                    \"This vendor bill was not (or could not be detected as) created from an employee expense sheet and cannot be cleared with an advance.\\n\\nOnly vendor bills created from employee expense sheets with the 'Clear from Advance' option can be cleared with advance.\\n\\nYou can use 'Link to Advance' to manually link a box or expense sheet.\"\n                )\n                raise UserError(error_msg)\n            else:\n                # flagged but no sheet: allow manager to provide advance_box_id or proceed with partner->employee detection\n                adv_box = self.advance_box_id\n                if not adv_box:\n                    employee = self._find_employee_from_partner()\n                    if employee:\n                        adv_box = self.env['employee.advance.box'].search([('employee_id', '=', employee.id)], limit=1)\n                if not adv_box:\n                    raise UserError(_('No advance box found for this bill. Please use Link to Advance or set an advance box on the bill.'))\n                return self._open_register_payment_wizard(adv_box)\n

        # If the expense sheet exists but is not linked to this bill, link it.
        if expense_sheet and expense_sheet.bill_id != self:
            _logger.info('Auto-linking expense sheet %s to bill %s for advance clearing', expense_sheet.name, self.name)
            expense_sheet.sudo().write({'bill_id': self.id})

        # If the expense sheet exists but doesn't have an advance_box_id,
        # check if we detected one separately and use the direct clearing method
        if expense_sheet and not expense_sheet.advance_box_id and self.advance_box_id:
            return self._open_register_payment_wizard(self.advance_box_id)
        elif expense_sheet and expense_sheet.advance_box_id:
            # Open register payment wizard instead of creating JE directly from expense sheet
            return self._open_register_payment_wizard(expense_sheet.advance_box_id)
        else:
            # If no expense sheet or no advance box, try using the advance_box_id on the bill itself
            if self.advance_box_id:
                return self._open_register_payment_wizard(self.advance_box_id)
            else:
                raise UserError(_('No advance box linked to this bill or its associated expense sheet.'))

    def _find_employee_from_partner(self):
        """Find employee associated with the bill partner through various methods"""
        # Method 1: Try to find employee using user_partner_id
        employee = self.env['hr.employee'].search([('user_partner_id', '=', self.partner_id.id)], limit=1)
        if employee:
            return employee

        # Method 2: Try to find employee by address_home_id (private address)
        employee = self.env['hr.employee'].search([('address_home_id', '=', self.partner_id.id)], limit=1)
        if employee:
            return employee

        # Method 3: Try to find employee by checking if this partner is linked to any employee
        # Look for employees where the partner matches any of the employee's partner fields
        all_employees = self.env['hr.employee'].search([])
        for emp in all_employees:
            emp_partner = emp._get_employee_partner()  # Use the method from advance_box
            if emp_partner and emp_partner == self.partner_id.id:
                return emp

        return None  # No employee found associated with this partner

    def _open_register_payment_wizard(self, advance_box):
        """Open the Register Payment wizard with default settings from advance box"""
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('The vendor bill must be posted before clearing the advance.'))
        if self.amount_residual <= 0:
            raise UserError(_('The vendor bill is already fully paid.'))

        # Get the advance box journal as the default payment method
        advance_journal = advance_box.journal_id
        if not advance_journal:
            raise UserError(_('The advance box does not have a journal configured. Please set a journal for the advance box.'))
        
        # Validate the advance box account
        if not advance_box.account_id:
            raise UserError(_('The advance box does not have an account configured.'))

        # Check if fiscal period is locked before proceeding
        company_id = advance_box.company_id or self.env.company
        locked_date = company_id._get_user_fiscal_lock_date()
        if fields.Date.context_today(self) <= locked_date:
            raise UserError(_("Cannot create payment before or during the lock date %s.", locked_date))

        # Prepare values for the payment wizard
        payment_vals = {
            'journal_id': advance_journal.id,
            'partner_id': self.partner_id.id,
            'partner_type': 'supplier',
            'payment_type': 'outbound',  # Payment to vendor/employee
            'amount': min(self.amount_residual, self.amount_total_signed),
            'currency_id': self.currency_id.id,
            'payment_difference_handling': 'open',
            'move_ids': [(4, self.id, False)],
        }

        # Create a payment wizard context with proper flags as per requirements
        action = {
            'name': _('Register Payment on Advance'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_model': 'account.move',
                'active_ids': [self.id],
                'force_advance_payment': True,  # Required flag from prompt
                'default_advance_box_id': advance_box.id,  # Required from prompt
                'default_journal_id': advance_journal.id,  # Pre-fill journal as per requirements
                **payment_vals
            },
        }
        
        return action

    def _clear_advance_using_advance_box(self, advance_box):
        """Create a clearing JE directly using the advance box when no expense sheet is available."""
        # This is a minimal flow similar to HrExpenseSheet.action_clear_advance but without a sheet
        # Create simple JE and reconcile with bill
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('The vendor bill must be posted before clearing the advance.'))
        if self.amount_residual <= 0:
            raise UserError(_('The vendor bill is already fully paid.'))

        clearing_journal_id = self.env['ir.config_parameter'].sudo().get_param('employee_advance.advance_default_clearing_journal_id')
        if not clearing_journal_id:
            raise UserError(_('Please set the default clearing journal in configuration.'))

        journal = self.env['account.journal'].browse(int(clearing_journal_id))
        if not journal:
            raise UserError(_('Invalid clearing journal configured.'))

        # Ensure the journal has a sequence configured so posting will generate unique names
        if not getattr(journal, 'sequence_id', False):
            raise UserError(_('The configured clearing journal (%s) does not have a sequence configured.\nPlease set a sequence on the journal so posted entries receive unique names.') % (journal.display_name,))

        # Determine the payable account from the bill
        payable_account = None
        for line in self.line_ids:
            if line.account_id.account_type == 'liability_payable' and line.balance < 0:
                payable_account = line.account_id
                break

        if not payable_account:
            raise UserError(_('Could not find payable account in the vendor bill.'))

        # Create journal entry to clear advance
        # Prepare journal entry values without a pre-set 'name' so the journal sequence
        # will assign a unique name upon posting. Also include company and move_type
        # to ensure sequences and constraints are applied correctly per company.
        je_vals = {
            'journal_id': journal.id,
            'company_id': journal.company_id.id if journal.company_id else self.company_id.id,
            'move_type': 'entry',
            'date': fields.Date.context_today(self),
            'ref': f'Clear Advance for {self.name}',
            'line_ids': [
                (0, 0, {
                    'account_id': payable_account.id,
                    'partner_id': self.partner_id.id,
                    'debit': abs(self.amount_residual),
                    'credit': 0.0,
                    'name': f'Clear Advance for {self.name}',
                }),
                (0, 0, {
                    'account_id': advance_box.account_id.id,
                    'partner_id': self.partner_id.id,
                    'debit': 0.0,
                    'credit': abs(self.amount_residual),
                    'name': f'Clear Advance for {self.name}',
                }),
            ]
        }

        # Ensure we don't set 'name' so the posting will use the journal sequence
        je = self.env['account.move'].create(je_vals)
        je.action_post()

        # Log in the chatter
        self.message_post(
            body=_("Advance cleared with journal entry %s. Dr %s, Cr %s" %
                  (je.name, payable_account.code, advance_box.account_id.code))
        )

        # Trigger recompute of the advance box balance
        try:
            advance_box._trigger_balance_recompute()
        except Exception:
            # Don't block clearing if recompute fails; could add logging here
            pass

        return je

    def action_post(self):
        """Override to handle advance clearing for payments"""
        # Don't override the action_post method for general moves
        # This was causing issues with duplicate processing
        # Only handle advance clearing in the payment context
        return super(AccountMove, self).action_post()


class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_advance_clearing = fields.Boolean(string='Is Advance Clearing', default=False)
    reconciled_bill_ids = fields.One2many('account.move', 'payment_id', string='Reconciled Bills')
        