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
        """Method to be called from vendor bill to clear advance"""
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
                    sheet_name = self.ref.split('Expense Sheet', 1)[1].strip()
                    # If the ref included other characters like ':' or '-', clean them
                    sheet_name = sheet_name.lstrip(':').strip()
                    if sheet_name:
                        expense_sheet = ExpenseSheet.search([('name', 'ilike', sheet_name)], limit=1)
            except Exception:
                _logger.debug('Failed to parse expense sheet name from bill ref: %s', self.ref)

        # If still not found, but the bill is flagged or context allows, try to detect employee via partner and advance box
        if not expense_sheet:
            if not is_flagged:
                # Try to detect employee from partner
                employee = self.env['hr.employee'].search([('user_partner_id', '=', self.partner_id.id)], limit=1)
                if employee:
                    # Find advance box for the employee
                    adv_box = self.env['employee.advance.box'].search([('employee_id', '=', employee.id)], limit=1)
                    if adv_box:
                        # allow proceed: create a minimal sheet placeholder? prefer to just set the advance box on bill
                        _logger.info('Detected employee %s from partner %s and found advance box %s for bill %s', employee.name, self.partner_id.name, adv_box.name, self.name)
                        self.sudo().write({'advance_box_id': adv_box.id})
                        # allow proceed without an expense sheet (some flows create direct JE)
                        return self._clear_advance_using_advance_box(adv_box)

                # No detection - raise
                error_msg = _(
                    "This vendor bill was not (or could not be detected as) created from an employee expense sheet and cannot be cleared with an advance.\n\nOnly vendor bills created from employee expense sheets with the 'Clear from Advance' option can be cleared with advance.\n\nYou can use 'Link to Advance' to manually link a box or expense sheet."
                )
                raise UserError(error_msg)
            else:
                # flagged but no sheet: allow manager to provide advance_box_id or proceed with partner->employee detection
                adv_box = self.advance_box_id
                if not adv_box:
                    employee = self.env['hr.employee'].search([('user_partner_id', '=', self.partner_id.id)], limit=1)
                    if employee:
                        adv_box = self.env['employee.advance.box'].search([('employee_id', '=', employee.id)], limit=1)
                if not adv_box:
                    raise UserError(_('No advance box found for this bill. Please use Link to Advance or set an advance box on the bill.'))
                return self._clear_advance_using_advance_box(adv_box)

        # If the expense sheet exists but is not linked to this bill, link it.
        if expense_sheet and expense_sheet.bill_id != self:
            _logger.info('Auto-linking expense sheet %s to bill %s for advance clearing', expense_sheet.name, self.name)
            expense_sheet.sudo().write({'bill_id': self.id})

        # If the expense sheet exists but doesn't have an advance_box_id,
        # check if we detected one separately and use the direct clearing method
        if expense_sheet and not expense_sheet.advance_box_id and self.advance_box_id:
            return self._clear_advance_using_advance_box(self.advance_box_id)
        elif expense_sheet and expense_sheet.advance_box_id:
            # Call the clear advance method from the expense sheet
            return expense_sheet.action_clear_advance()
        else:
            # If no expense sheet or no advance box, try using the advance_box_id on the bill itself
            if self.advance_box_id:
                return self._clear_advance_using_advance_box(self.advance_box_id)
            else:
                raise UserError(_('No advance box linked to this bill or its associated expense sheet.'))

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
        clearing_journal = self.env['account.journal'].browse(int(clearing_journal_id))
        if not clearing_journal.exists():
            raise UserError(_('Clearing journal not found. Please check configuration.'))

        residual_amount = self.amount_residual
        target_partner_id = self.partner_id.id

        je_vals = {
            'journal_id': clearing_journal.id,
            'date': fields.Date.context_today(self),
            'ref': f'Clear Advance for Bill {self.name}',
            'line_ids': [
                (0, 0, {
                    'account_id': self.partner_id.property_account_payable_id.id,
                    'partner_id': target_partner_id,
                    'debit': residual_amount,
                    'credit': 0.0,
                    'name': f'Clear Advance for Bill {self.name}'
                }),
                (0, 0, {
                    'account_id': advance_box.account_id.id,
                    'partner_id': target_partner_id,
                    'debit': 0.0,
                    'credit': residual_amount,
                    'name': f'Clear Advance for Bill {self.name}'
                }),
            ]
        }
        je = self.env['account.move'].create(je_vals)
        je.action_post()

        ap_line_from_je = je.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
        ap_line_from_bill = self.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
        if ap_line_from_je and ap_line_from_bill:
            (ap_line_from_je + ap_line_from_bill).reconcile()

        self.message_post(body=_('Advance cleared via journal entry %s.' % je.name))
        advance_box.message_post(body=_('Advance cleared for bill %s via journal entry %s.' % (self.name, je.name)))
        return je