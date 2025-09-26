from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    use_advance = fields.Boolean(
        string='Clear from Advance',
        default=True
    )
    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        domain="[('employee_id', '=', employee_id), ('company_id', '=', company_id)]"
    )
    bill_id = fields.Many2one(
        'account.move',
        string='Vendor Bill',
        copy=False
    )
    payment_ids = fields.Many2many(
        'account.payment',
        string='Payments',
        compute='_compute_payment_ids'
    )

    @api.depends('bill_id')
    def _compute_payment_ids(self):
        for sheet in self:
            if sheet.bill_id:
                # Find payments that are reconciled with the bill
                reconciled_payments = self.env['account.payment']
                for line in sheet.bill_id.line_ids:
                    if line.account_id.account_type == 'liability_payable':
                        for partial_line in line.matched_debit_ids + line.matched_credit_ids:
                            payment = partial_line.debit_move_id.move_id or partial_line.credit_move_id.move_id
                            if payment._name == 'account.payment':
                                reconciled_payments |= payment
                sheet.payment_ids = reconciled_payments
            else:
                sheet.payment_ids = [(5, 0, 0)]  # Empty

    @api.onchange('use_advance')
    def _onchange_use_advance(self):
        """Clear advance box if not using advance"""
        if not self.use_advance:
            self.advance_box_id = False

    def action_approve_expense_sheets(self):
        """Override approval to create draft vendor bill when using advance"""
        res = super(HrExpenseSheet, self).action_approve_expense_sheets()
        
        for sheet in self:
            if sheet.use_advance and sheet.advance_box_id:
                sheet._create_vendor_bill_and_activity()
        
        return res

    def _create_vendor_bill_and_activity(self):
        """Create vendor bill and activity for accounting team"""
        self.ensure_one()
        
        # Check if employee has private address
        employee = self.employee_id
        # Check if employee has private address using the same logic as advance box
        partner_id = False
        
        # Method 1: Check if address_home_id exists (from hr_contract module)
        if hasattr(employee, 'address_home_id'):
            partner_id = employee.sudo().address_home_id.id if employee.sudo().address_home_id else False
        
        # If still not found, try to get the related user's partner (which might contain private address)
        if not partner_id and employee.user_id:
            partner_id = employee.user_id.partner_id.id
        
        # If still not found, default to employee's address_id (work address)
        if not partner_id:
            partner_id = employee.address_id.id if employee.address_id else False
        
        if not partner_id:
            raise UserError(_(
                "Employee %s does not have a private address. Please set the employee's home address."
            ) % employee.name)
        
        # Check if advance account is set
        advance_box = self.advance_box_id
        if not advance_box.account_id:
            raise UserError(_("Please set the advance account for the selected advance box."))
        
        # Create vendor bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': partner_id,
            'invoice_date': fields.Date.context_today(self),
            'date': fields.Date.context_today(self),
            'currency_id': self.currency_id.id,
            'company_id': self.company_id.id,
            'ref': f'Expense Sheet {self.name}',
            'invoice_line_ids': [],
        }
        
        # Add expense lines to the bill
        for expense in self.expense_line_ids:
            bill_line_vals = {
                'name': expense.name,
                'quantity': expense.quantity,
                'price_unit': expense.price_unit,
                'tax_ids': [(6, 0, expense.tax_ids.ids)],
                'account_id': expense.account_id.id,
            }
            bill_vals['invoice_line_ids'].append((0, 0, bill_line_vals))
        
        bill = self.env['account.move'].create(bill_vals)
        
        # Link bill to expense sheet and also set advance box reference on the bill
        self.bill_id = bill.id
        # Also link the advance box to the bill for easier tracking
        bill.sudo().write({
            'advance_box_id': self.advance_box_id.id,
            'expense_sheet_id': self.id,
            'is_expense_advance_bill': True
        })
        
        # Add activity for accounting as per settings
        ICP = self.env['ir.config_parameter'].sudo()
        user_id = int(ICP.get_param('employee_advance.advance_notify_user_id', 0))
        group_id = int(ICP.get_param('employee_advance.advance_notify_group_id', 0))
        activity_type_id = int(ICP.get_param('employee_advance.advance_notify_activity_type_id', 0))
        deadline_days = int(ICP.get_param('employee_advance.advance_notify_deadline_days', 1))
        
        activity_vals = {
            'res_id': bill.id,
            'res_model_id': self.env['ir.model']._get_id('account.move'),
            'activity_type_id': activity_type_id or self.env.ref('employee_advance.mail_activity_type_advance_bill_review').id,
            'summary': f'Review vendor bill for expense sheet {self.name}',
            'user_id': user_id or self.env.ref('base.user_admin').id,
            'date_deadline': fields.Date.add(fields.Date.context_today(self), days=deadline_days),
        }
        
        if group_id:
            activity_vals['user_id'] = self.env['res.users'].search([('groups_id', '=', group_id)], limit=1).id or activity_vals['user_id']
        
        bill.activity_schedule(
            activity_type_id=activity_vals['activity_type_id'],
            summary=activity_vals['summary'],
            note=f"Expense sheet {self.name} has been approved. Please review the vendor bill.",
            user_id=activity_vals['user_id'],
            date_deadline=activity_vals['date_deadline']
        )
        
        # Log in chatter
        bill.message_post(body=_("Vendor bill created from expense sheet approval."))
        
        return bill

    def action_clear_advance(self):
        """Clear advance by creating JE and reconciling"""
        for sheet in self:
            if not sheet.bill_id:
                raise UserError(_("No vendor bill found for this expense sheet."))
            
            if sheet.bill_id.state != 'posted':
                raise UserError(_("The vendor bill must be posted before clearing the advance."))
            
            if sheet.bill_id.amount_residual <= 0:
                raise UserError(_("The vendor bill is already fully paid."))
            
            advance_box = sheet.advance_box_id
            if not advance_box:
                raise UserError(_("No advance box selected."))
            
            if not advance_box.account_id:
                raise UserError(_("Please set the advance account for the selected advance box."))
            
            # Check if employee has private address using the same logic as above
            partner_id = False
            
            # Method 1: Check if address_home_id exists (from hr_contract module)
            if hasattr(advance_box.employee_id, 'address_home_id'):
                partner_id = advance_box.employee_id.sudo().address_home_id.id if advance_box.employee_id.sudo().address_home_id else False
            
            # If still not found, try to get the related user's partner (which might contain private address)
            if not partner_id and advance_box.employee_id.user_id:
                partner_id = advance_box.employee_id.user_id.partner_id.id
            
            # If still not found, default to employee's address_id (work address)
            if not partner_id:
                partner_id = advance_box.employee_id.address_id.id if advance_box.employee_id.address_id else False
            
            if not partner_id:
                raise UserError(_("Please set the employee's private address."))
                
            # Check if default clearing journal is set in config
            clearing_journal_id = self.env['ir.config_parameter'].sudo().get_param('employee_advance.advance_default_clearing_journal_id')
            if not clearing_journal_id:
                raise UserError(_("Please set the default clearing journal in configuration."))
            
            clearing_journal = self.env['account.journal'].browse(int(clearing_journal_id))
            if not clearing_journal.exists():
                raise UserError(_("Clearing journal not found. Please check configuration."))
            
            # Create journal entry to clear advance
            residual_amount = sheet.bill_id.amount_residual
            # Use the partner_id from the address check above
            target_partner_id = sheet.bill_id.partner_id.id
            
            je_vals = {
                'journal_id': clearing_journal.id,
                'date': fields.Date.context_today(sheet),
                'ref': f'Clear Advance for Bill {sheet.bill_id.name}',
                'line_ids': [
                    (0, 0, {
                        'account_id': sheet.bill_id.partner_id.property_account_payable_id.id,
                        'partner_id': target_partner_id,
                        'debit': residual_amount,
                        'credit': 0.0,
                        'name': f'Clear Advance for Bill {sheet.bill_id.name}'
                    }),
                    (0, 0, {
                        'account_id': advance_box.account_id.id,
                        'partner_id': target_partner_id,
                        'debit': 0.0,
                        'credit': residual_amount,
                        'name': f'Clear Advance for Bill {sheet.bill_id.name}'
                    }),
                ]
            }
            
            je = self.env['account.move'].create(je_vals)
            je.action_post()  # Post the journal entry
            
            # Now reconcile the AP line from the JE with the bill's AP line
            ap_line_from_je = je.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
            ap_line_from_bill = sheet.bill_id.line_ids.filtered(lambda l: l.account_id.account_type == 'liability_payable')
            
            if ap_line_from_je and ap_line_from_bill:
                lines_to_reconcile = ap_line_from_je + ap_line_from_bill
                if lines_to_reconcile:
                    lines_to_reconcile.reconcile()
            
            # Update expense sheet and bill
            sheet.message_post(body=_("Advance cleared via journal entry %s." % je.name))
            sheet.bill_id.message_post(body=_("Advance cleared via journal entry %s." % je.name))
            
            # Log in advance box
            advance_box.message_post(body=_("Advance cleared for expense sheet %s via journal entry %s." % (sheet.name, je.name)))
            
            return je

    def action_sheet_paid(self):
        """Override method to handle paid status after advance clearing"""
        # Only change the state to done if not already done
        if self.state != 'done':
            self.write({'state': 'done'})
        return True