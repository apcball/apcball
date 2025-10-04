# Copyright 2024
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class HrExpenseSheet(models.Model):
    _inherit = 'hr.expense.sheet'

    def _create_vendor_bill_and_activity(self):
        """Create vendor bill and activity for accounting team with WHT support"""
        self.ensure_one()

        # Check if employee has private address
        employee = self.employee_id
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
            
        # Ensure the partner name matches the employee name to show proper name in vendor field
        partner = self.env['res.partner'].browse(partner_id)
        if partner and partner.name != employee.name:
            # Update the partner's name to match the employee's name for proper vendor display
            # Only do this if it's likely a user partner that shows user ID instead of employee name
            partner.write({'name': employee.name})

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

        # Add expense lines to the bill with potential WHT
        for expense in self.expense_line_ids:
            bill_line_vals = {
                'name': expense.name,
                'quantity': expense.quantity,
                'price_unit': expense.price_unit,
                'tax_ids': [(6, 0, expense.tax_ids.ids)],
                'account_id': expense.account_id.id,
            }
            
            # Add WHT tax if available on the expense
            if hasattr(expense, 'wht_tax_id') and expense.wht_tax_id:
                bill_line_vals['wht_tax_id'] = expense.wht_tax_id.id
                
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

    def _check_bill_has_wht(self, bill):
        """Check if the bill has WHT lines or WHT tax on any line"""
        if not bill:
            return False
        
        # Check if any line has wht_tax_id or if the move has wht_move_ids
        has_wht = any(
            hasattr(line, 'wht_tax_id') and line.wht_tax_id 
            for line in bill.invoice_line_ids
        )
        
        # Also check if there are existing WHT moves
        if not has_wht and hasattr(bill, 'wht_move_ids'):
            has_wht = bool(bill.wht_move_ids)
        
        # If no WHT found at line level, check for any line with WHT tax in tax_ids
        if not has_wht:
            has_wht = any(
                tax.amount < 0 and 'wht' in tax.name.lower() 
                for line in bill.invoice_line_ids 
                for tax in line.tax_ids
            )
        
        return has_wht


    def _get_base_amount_excluding_vat(self, invoice_line):
        """Calculate base amount excluding VAT for WHT calculation (base amount that VAT was calculated on)"""
        # Calculate the base amount before VAT was added
        # This is important for WHT calculation since WHT should be calculated on base amount
        # If there are VAT taxes, we need to remove them to get the base
        price_unit = invoice_line.price_unit
        quantity = invoice_line.quantity
        subtotal = price_unit * quantity
        
        # Get all VAT taxes (positive amount for purchases)
        vat_taxes = invoice_line.tax_ids.filtered(lambda t: t.amount > 0)
        
        # If there are VAT taxes, calculate the base amount before VAT
        if vat_taxes:
            # Calculate the tax amount to subtract
            # We need to calculate the base amount before tax, not including tax
            # Use the same method Odoo uses to calculate the base
            tax_compute_all = vat_taxes.compute_all(
                price_unit=price_unit,
                currency=invoice_line.currency_id,
                quantity=quantity,
                product=invoice_line.product_id,
                partner=invoice_line.partner_id
            )
            
            # The base amount for tax calculation is in 'base' field of the first tax
            # However, for WHT we want the amount that VAT was calculated on
            # This is the amount before VAT was added
            base_amount = tax_compute_all['total_excluded']  # Amount before VAT (tax included)
        else:
            # If no VAT, the base amount is just the subtotal
            base_amount = subtotal
        
        return base_amount

    def _create_wht_journal_entries(self, bill, advance_box):
        """Create WHT journal entries based on WHT lines in the bill"""
        if not bill or not self._check_bill_has_wht(bill):
            return None

        # Find WHT lines in the bill
        wht_lines = bill.invoice_line_ids.filtered(lambda l: l.wht_tax_id)
        
        if not wht_lines:
            # Look for lines that have taxes that are withholding taxes
            wht_tax_taxes = bill.invoice_line_ids.mapped('tax_ids').filtered(
                lambda t: t.amount < 0 and (t.l10n_th_is_withholding or 'wht' in t.name.lower() or t.type_tax_use == 'none')
            )
            wht_lines = bill.invoice_line_ids.filtered(
                lambda l: any(tax in wht_tax_taxes for tax in l.tax_ids)
            )
        
        if not wht_lines:
            return None

        # Get the clearing journal from configuration
        clearing_journal_id = self.env['ir.config_parameter'].sudo().get_param('employee_advance.advance_default_clearing_journal_id')
        if not clearing_journal_id:
            raise UserError(_('Please set the default clearing journal in configuration.'))
        
        journal = self.env['account.journal'].browse(int(clearing_journal_id))
        if not journal:
            raise UserError(_('Invalid clearing journal configured.'))
        
        # Ensure the journal has a sequence configured
        self.env['hr.expense.advance.journal.utils'].ensure_journal_sequence(journal)

        # Track total WHT amounts
        wht_entries = []
        total_wht_amount = 0.0
        
        for line in wht_lines:
            # Calculate base amount excluding VAT for this line
            base_amount = self._get_base_amount_excluding_vat(line)
            
            # Get WHT tax (could be from line.wht_tax_id or from line.tax_ids)
            wht_tax = line.wht_tax_id
            if not wht_tax:
                # Get the first WHT tax from the line's taxes
                wht_tax = line.tax_ids.filtered(
                    lambda t: t.amount < 0 and (t.l10n_th_is_withholding or 'wht' in t.name.lower())
                )[:1]
            
            if not wht_tax:
                continue  # Skip if no WHT tax found
                
            # Calculate WHT amount based on base amount excluding VAT
            wht_amount = abs(base_amount * (wht_tax.amount / 100))
            total_wht_amount += wht_amount

            # Get WHT payable account from tax configuration
            wht_payable_account = None
            wht_tax_repartition = wht_tax.invoice_repartition_line_ids.filtered(
                lambda r: r.repartition_type == 'tax' and r.account_id
            )
            if wht_tax_repartition:
                wht_payable_account = wht_tax_repartition[0].account_id
            else:
                # Fallback: look for common WHT payable account names
                wht_payable_account = self.env['account.account'].search([
                    ('name', 'ilike', 'withholding'),
                    ('account_type', '=', 'liability_current'),
                    ('company_id', '=', bill.company_id.id)
                ], limit=1)
            
            if not wht_payable_account:
                raise UserError(_(
                    "No WHT payable account found for tax %s. Please configure the WHT tax account."
                ) % wht_tax.name)

            # Add the WHT journal entry lines
            wht_entries.append((0, 0, {
                'name': f'WHT Payable - {wht_tax.name} for {line.name}',
                'account_id': wht_payable_account.id,
                'partner_id': bill.partner_id.id,
                'debit': 0.0,
                'credit': wht_amount,
                'tax_line_id': wht_tax.id,
                'tax_base_amount': base_amount,
            }))

        if not wht_entries:
            return None  # No WHT entries to create

        # Get payable account from the bill
        payable_account = None
        for line in bill.line_ids:
            if line.account_id.account_type == 'liability_payable' and line.balance < 0:
                payable_account = line.account_id
                break

        if not payable_account:
            raise UserError(_('Could not find payable account in the vendor bill.'))

        # Create journal entry to record WHT
        je_vals = {
            'journal_id': journal.id,
            'company_id': journal.company_id.id if journal.company_id else bill.company_id.id,
            'move_type': 'entry',
            'date': fields.Date.context_today(bill),
            'ref': f'WHT for Advance Clearing of {bill.name}',
            'line_ids': [
                # Dr. Payable Account (increase payable account due to WHT)
                (0, 0, {
                    'account_id': payable_account.id,
                    'partner_id': bill.partner_id.id,
                    'debit': wht_amount,  # The amount increases due to WHT deduction
                    'credit': 0.0,
                    'name': f'WHT deduction for {bill.name}',
                }),
            ] + wht_entries  # Add WHT payable lines
        }

        # Create the journal entry
        wht_je = self.env['account.move'].create(je_vals)
        wht_je.action_post()

        # Log in the bill's chatter
        bill.message_post(
            body=_("WHT journal entries created: %s. Total WHT: %.2f") % 
                  (wht_je.name, total_wht_amount)
        )

        # Also create WHT certificates if possible
        try:
            if hasattr(bill, 'create_wht_cert_from_advance_clearing'):
                bill.create_wht_cert_from_advance_clearing()
        except Exception as e:
            _logger.warning(f"Could not create WHT certificates: {e}")

        return wht_je

    has_wht_certs = fields.Boolean(
        string='Has WHT Certificates',
        compute='_compute_has_wht_certs',
        store=True
    )
    
    bill_id_has_wht_line = fields.Boolean(
        string='Bill Has WHT Lines',
        compute='_compute_bill_id_has_wht_line',
        store=True
    )

    @api.depends('bill_id', 'bill_id.wht_cert_ids')
    def _compute_has_wht_certs(self):
        """Compute if the associated vendor bill has WHT certificates"""
        for sheet in self:
            if sheet.bill_id and sheet.bill_id.wht_cert_ids:
                sheet.has_wht_certs = True
            else:
                sheet.has_wht_certs = False
    
    @api.depends('bill_id', 'bill_id.has_wht_line')
    def _compute_bill_id_has_wht_line(self):
        """Compute if the associated vendor bill has WHT lines"""
        for sheet in self:
            if sheet.bill_id:
                sheet.bill_id_has_wht_line = sheet.bill_id.has_wht_line
            else:
                sheet.bill_id_has_wht_line = False


class AccountMove(models.Model):
    _inherit = 'account.move'

    # Add computed field to check if invoice lines have WHT taxes
    has_wht_line = fields.Boolean(
        string='Has WHT Lines',
        compute='_compute_has_wht_line',
        store=True
    )

    @api.depends('invoice_line_ids', 'invoice_line_ids.wht_tax_id')
    def _compute_has_wht_line(self):
        """Compute if any invoice line has WHT tax"""
        for move in self:
            if move.move_type in ['in_invoice', 'in_refund'] and move.invoice_line_ids:
                move.has_wht_line = any(line.wht_tax_id for line in move.invoice_line_ids)
            else:
                move.has_wht_line = False

    def _clear_advance_using_advance_box(self, advance_box):
        """Create a clearing JE directly using the advance box when no expense sheet is available with WHT support."""
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
        # Use the utility to create sequence if missing
        self.env['hr.expense.advance.journal.utils'].ensure_journal_sequence(journal)

        # Determine the payable account from the bill
        payable_account = None
        for line in self.line_ids:
            if line.account_id.account_type == 'liability_payable' and line.balance < 0:
                payable_account = line.account_id
                break

        if not payable_account:
            raise UserError(_('Could not find payable account in the vendor bill.'))

        # Check if vendor bill has withholding tax, and if so, we need to create both 
        # the clearing entry and a WHT certificate
        has_wht = any(line.wht_tax_id for line in self.invoice_line_ids)
        
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

        # Automatically reconcile the journal entry with the original vendor bill
        # Find payable lines in both the original bill and the new journal entry
        original_payable_line = self.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable' and line.balance < 0
        )[:1]  # Take the first payable line

        je_payable_line = je.line_ids.filtered(
            lambda line: line.account_id.id == payable_account.id and line.debit > 0
        )[:1]  # Take the first payable line from the JE

        if original_payable_line and je_payable_line:
            # Prepare lines for reconciliation
            lines_to_reconcile = (original_payable_line + je_payable_line).sorted()
            if lines_to_reconcile and len(lines_to_reconcile.mapped('account_id')) == 1:
                try:
                    # Attempt reconciliation
                    lines_to_reconcile.reconcile()
                except Exception as e:
                    # If reconciliation fails, log but don't fail the entire operation
                    _logger.warning(f"Could not reconcile advance clearing entry: {e}")

        # Log in the chatter
        self.message_post(
            body=_("Advance cleared with journal entry %s. Dr %s, Cr %s" %
                  (je.name, payable_account.code, advance_box.account_id.code))
        )

        # Trigger recompute of the advance box balance with safe method - HANG FIX
        try:
            advance_box._refresh_balance_simple()
            _logger.info("💰 Advance box balance refreshed after clearing")
        except Exception as e:
            # Don't block clearing if recompute fails - HANG FIX
            _logger.warning("⚠️ Balance refresh failed after clearing, but operation succeeded: %s", str(e))

        # If the original bill had withholding tax, we should create WHT certificate(s)
        if has_wht:
            try:
                # Create WHT certificate from the original vendor bill that was cleared
                if self.wht_move_ids:
                    # Use existing method to create WHT certificates if withholding moves exist
                    self.create_wht_cert()
            except Exception as e:
                # Log error if WHT certificate creation fails, but don't interrupt the clearing
                _logger.warning(f"Could not create WHT certificate for advance clearing: {e}")

        return je

    def action_clear_advance_from_bill(self):
        """Method to be called from vendor bill to clear advance - creates Journal Entry instead of opening Register Payment wizard"""
        self.ensure_one()
        
        # If the bill already has explicit metadata set, prefer it
        ExpenseSheet = self.env['hr.expense.sheet']
        expense_sheet = self.expense_sheet_id or ExpenseSheet.search([('bill_id', '=', self.id)], limit=1)

        # If the bill was explicitly flagged as an expense advance bill, allow proceed
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

        # If still not found, but the bill is flagged or context allows, try to detect employee via partner and advance box
        if not expense_sheet:
            if not is_flagged:
                # Try to detect employee from partner using multiple methods
                employee = self._find_employee_from_partner()
                if employee:
                    # Find advance box for the employee
                    adv_box = self.env['employee.advance.box'].search([('employee_id', '=', employee.id)], limit=1)
                    if adv_box:
                        # allow proceed: create a minimal sheet placeholder? prefer to just set the advance box on bill
                        _logger.info('Detected employee %s from partner %s and found advance box %s for bill %s', employee.name, self.partner_id.name, adv_box.name, self.name)
                        self.sudo().write({'advance_box_id': adv_box.id})
                        # Create Journal Entry instead of opening Register Payment wizard
                        result = self._clear_advance_using_advance_box(adv_box)
                        return result

                # No detection - raise
                error_msg = _(
                    "This vendor bill was not (or could not be detected as) created from an employee expense sheet and cannot be cleared with an advance.\n\nOnly vendor bills created from employee expense sheets with the 'Clear from Advance' option can be cleared with advance.\n\nYou can use 'Link to Advance' to manually link a box or expense sheet."
                )
                raise UserError(error_msg)
            else:
                # flagged but no sheet: allow manager to provide advance_box_id or proceed with partner->employee detection
                adv_box = self.advance_box_id
                if not adv_box:
                    employee = self._find_employee_from_partner()
                    if employee:
                        adv_box = self.env['employee.advance.box'].search([('employee_id', '=', employee.id)], limit=1)
                        if adv_box:
                            # Set the advance_box_id on the bill for consistency
                            self.sudo().write({'advance_box_id': adv_box.id})

                if not adv_box:
                    raise UserError(_('No advance box detected from bill partner. Please use the link wizard or create an advance box for the employee.'))

                # Create Journal Entry instead of opening Register Payment wizard
                result = self._clear_advance_using_advance_box(adv_box)
                return result

        # If the expense sheet exists but is not linked to this bill, link it.
        if expense_sheet and expense_sheet.bill_id != self:
            _logger.info('Auto-linking expense sheet %s to bill %s for advance clearing', expense_sheet.name, self.name)
            expense_sheet.sudo().write({'bill_id': self.id})

        # If the expense sheet exists but doesn't have an advance_box_id,
        # check if we detected one separately and use the direct clearing method
        if expense_sheet and not expense_sheet.advance_box_id and self.advance_box_id:
            result = self._clear_advance_using_advance_box(self.advance_box_id)
            return result
        elif expense_sheet and expense_sheet.advance_box_id:
            # Create Journal Entry instead of opening Register Payment wizard from expense sheet
            result = self._clear_advance_using_advance_box(expense_sheet.advance_box_id)
            return result
        else:
            # If no expense sheet or no advance box, try using the advance_box_id on the bill itself
            if self.advance_box_id:
                result = self._clear_advance_using_advance_box(self.advance_box_id)
                return result
            else:
                raise UserError(_('No advance box linked to this bill or its associated expense sheet.'))

    def create_wht_cert_from_advance_clearing(self):
        """
        Create WHT certificate from advance clearing for transactions that involved tax withholding.
        This method can be used when clearing advances where WHT applies.
        """
        self.ensure_one()
        
        # Check for any WHT moves associated with this move
        if not self.wht_move_ids:
            # If no existing WHT moves, check if we should create them based on invoice lines
            if hasattr(self, 'invoice_line_ids'):
                wht_lines = self.invoice_line_ids.filtered('wht_tax_id')
                if wht_lines:
                    # Create WHT moves based on invoice lines with WHT
                    for line in wht_lines:
                        amount_income = line.price_subtotal  # or appropriate base amount
                        amount_wht = line.price_subtotal * (line.wht_tax_id.amount / 100) if line.wht_tax_id.amount else 0.0
                        
                        self.env['account.withholding.move'].create({
                            'move_id': self.id,
                            'partner_id': self.partner_id.id,
                            'amount_income': amount_income,
                            'amount_wht': amount_wht,
                            'wht_tax_id': line.wht_tax_id.id,
                            'wht_cert_income_type': line.wht_tax_id.wht_cert_income_type or '5',
                            'company_id': self.company_id.id,
                        })
        
        # Now create WHT certificates using the existing method if WHT moves exist
        if self.wht_move_ids:
            # Make sure Type of Income is set on all WHT moves
            for w in self.wht_move_ids.filtered(lambda w: not w.wht_cert_income_type):
                if w.wht_tax_id and w.wht_tax_id.wht_cert_income_type:
                    w.write({'wht_cert_income_type': w.wht_tax_id.wht_cert_income_type})
                else:
                    # Fallback: use default "5" (ค่าจ้างทำของ ค่าบริการ ค่าเช่า ค่าขนส่ง ฯลฯ 3 เตรส)
                    w.write({'wht_cert_income_type': '5'})
            
            try:
                certs = self._preapare_wht_certs()
                created_certs = self.env['withholding.tax.cert'].create(certs)
                
                # Log creation in chatter
                self.message_post(
                    body=_("Withholding Tax Certificates created: %s") % 
                    ", ".join([cert.number for cert in created_certs if cert.number and cert.number != '/'])
                )
                
                return created_certs
            except Exception as e:
                _logger.error(f"Error creating WHT certificates for advance clearing: {e}")
                raise


class EmployeeAdvanceBox(models.Model):
    _inherit = 'employee.advance.box'

    def action_refill_to_base(self):
        """Open wizard to refill advance box to base amount with potential for WHT"""
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


class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def action_create_payments(self):
        """Override to support WHT certificate creation when advance payments are made"""
        # Call the original method
        res = super(AccountPaymentRegister, self).action_create_payments()
        
        # Check if this is an advance payment and if WHT needs to be processed
        if self.env.context.get('from_advance_clearing'):
            # Process WHT certificates for advance clearing if needed
            active_ids = self.env.context.get('active_ids')
            active_model = self.env.context.get('active_model')
            
            if active_model == 'account.move' and active_ids:
                moves = self.env['account.move'].browse(active_ids)
                for move in moves:
                    if move.wht_move_ids:
                        try:
                            move.create_wht_cert()
                        except Exception as e:
                            _logger.warning(f"Could not create WHT certificate for advance payment: {e}")
        
        return res