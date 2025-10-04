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
    
    # WHT Certificate support
    wht_tax_id = fields.Many2one('account.tax', string='WHT Tax', copy=False)
    wht_base_amount = fields.Monetary(string='WHT Base Amount', currency_field='currency_id', copy=False)
    wht_amount = fields.Monetary(string='WHT Amount', currency_field='currency_id', copy=False)
    is_advance_clearing = fields.Boolean(string='Is Advance Clearing Entry', default=False, copy=False)
    
    # WHT Certificate count for smart button
    wht_cert_count = fields.Integer(
        string='WHT Certificate Count',
        compute='_compute_wht_cert_count'
    )

    @api.depends('line_ids')
    def _compute_wht_cert_count(self):
        for move in self:
            count = 0
            try:
                # Check if WHT certificate module is installed
                if 'withholding.tax.cert' in self.env.registry:
                    WhtCert = self.env['withholding.tax.cert']
                    count = WhtCert.search_count([
                        ('move_id', '=', move.id)
                    ])
            except Exception:
                count = 0
            move.wht_cert_count = count

    has_wht_certs_available = fields.Boolean(
        string='Has WHT Certs Available',
        compute='_compute_has_wht_certs_available',
        help='True if WHT certificates can be created for this bill'
    )

    @api.depends('is_advance_clearing', 'wht_tax_id', 'wht_amount', 'has_wht_line', 'move_type')
    def _compute_has_wht_certs_available(self):
        """Compute if WHT certificates are available for this move"""
        for move in self:
            has_wht_certificates_available = False
            
            # Check for advance clearing entries with WHT
            if move.is_advance_clearing and move.wht_tax_id and move.wht_amount > 0:
                has_wht_certificates_available = True
            
            # Check for regular bills with WHT lines
            elif move.move_type == 'in_invoice' and move.has_wht_line:
                has_wht_certificates_available = True
            
            # Check for bills with WHT taxes (using safer approach)
            elif move.move_type == 'in_invoice':
                try:
                    # Check for WHT taxes by name pattern (safer than field that might not exist)
                    for line in move.invoice_line_ids:
                        for tax in line.tax_ids:
                            # Check common WHT tax patterns
                            if any(pattern in tax.name.lower() for pattern in ['wht', 'withholding', 'หัก ณ ที่จ่าย']):
                                has_wht_certificates_available = True
                                break
                            # Check for negative tax amounts (typical for WHT)
                            if tax.amount < 0:
                                has_wht_certificates_available = True
                                break
                        if has_wht_certificates_available:
                            break
                except Exception:
                    # Fallback to False if any error occurs
                    has_wht_certificates_available = False
            
            move.has_wht_certs_available = has_wht_certificates_available

    def can_create_wht_certificate(self):
        """Check if WHT certificate can be created from this move"""
        self.ensure_one()
        return (
            self.is_advance_clearing and 
            self.wht_tax_id and 
            self.wht_amount > 0 and
            'withholding.tax.cert' in self.env.registry
        )

    def action_create_wht_certificate(self):
        """Create WHT certificate or show information"""
        self.ensure_one()
        
        # Check if WHT certificate module is available
        if 'withholding.tax.cert' not in self.env.registry:
            # Show a helpful message instead of raising an error
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WHT Certificate Module Not Available'),
                    'message': _(
                        'The Thai Withholding Tax Certificate module is not available.\n\n'
                        'You can still create WHT certificates manually through:\n'
                        '• Accounting → Vendors → Withholding Tax Certificates\n'
                        '• Or install the WHT certificate modules if available\n\n'
                        'The WHT journal entry has been created successfully with:\n'
                        '• Base Amount: %s\n'
                        '• WHT Amount: %s\n'
                        '• Tax Rate: %s%%'
                    ) % (
                        self.wht_base_amount or 0.0,
                        self.wht_amount or 0.0, 
                        abs(self.wht_tax_id.amount) if self.wht_tax_id else 0.0
                    ),
                    'type': 'info',
                    'sticky': False,
                }
            }
        
        try:
            # Open new WHT certificate form with pre-filled context
            WhtCert = self.env['withholding.tax.cert']
            
            # Find WHT move lines for reference
            wht_lines = self.line_ids.filtered(lambda l: l.tax_line_id == self.wht_tax_id)
            
            # Get WHT partner (vendor) from WHT line, fallback to move partner
            wht_partner = self.partner_id
            if wht_lines:
                wht_partner = wht_lines[0].partner_id or self.partner_id
            
            # Prepare context with default values
            context = {
                'default_company_id': self.company_id.id,
                'default_partner_id': wht_partner.id,  # ใช้ vendor partner จาก WHT line
                'default_date': self.date,
                'default_move_id': self.id,
                'default_state': 'draft',
            }
            
            # Add WHT information if available
            if self.wht_tax_id:
                # Calculate tax rate percentage
                tax_rate = abs(self.wht_tax_id.amount) if self.wht_tax_id else 0.0
                
                # Find corresponding account.withholding.tax record
                wht_tax_domain = [
                    ('name', 'ilike', self.wht_tax_id.name),
                    ('amount', '=', self.wht_tax_id.amount),
                ]
                
                # Try to find the withholding tax record
                withholding_tax = None
                if 'account.withholding.tax' in self.env.registry:
                    withholding_tax = self.env['account.withholding.tax'].search(wht_tax_domain, limit=1)
                
                # Prepare WHT line data for the certificate
                wht_line_vals = {
                    'base': self.wht_base_amount or 0.0,
                    'amount': self.wht_amount or 0.0,
                    'wht_percent': tax_rate,
                    'wht_cert_income_type': '2',  # Default to type 2 (fees, commission)
                    'wht_cert_income_desc': _('Advance clearing payment'),
                }
                
                # Add withholding tax if found
                if withholding_tax:
                    wht_line_vals['wht_tax_id'] = withholding_tax.id
                
                context.update({
                    # Pre-fill the WHT line
                    'default_wht_line': [(0, 0, wht_line_vals)],
                    # Additional reference information
                    'default_ref': _('Advance Clearing - %s') % (self.ref or self.name),
                    'default_origin': self.name,
                    'default_description': _('WHT from advance clearing entry: %s') % self.name,
                })
            
            return {
                'type': 'ir.actions.act_window',
                'name': _('Create WHT Certificate'),
                'res_model': 'withholding.tax.cert',
                'view_mode': 'form',
                'target': 'new',
                'context': context,
            }
            
        except Exception as e:
            _logger.warning("Failed to open WHT certificate form: %s", str(e))
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WHT Certificate Form Unavailable'),
                    'message': _(
                        'Could not open WHT certificate form: %s\n\n'
                        'You can create WHT certificates manually through the Accounting menu.\n'
                        'The advance clearing journal entry has been created successfully.'
                    ) % str(e),
                    'type': 'warning',
                    'sticky': True,
                }
            }

    def action_view_wht_certificates(self):
        """View related WHT certificates"""
        self.ensure_one()
        
        if 'withholding.tax.cert' not in self.env.registry:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('WHT Certificate Module Not Available'),
                    'message': _('The WHT Certificate module is not installed. Please install the Thai localization modules.'),
                    'type': 'info',
                }
            }

        try:
            WhtCert = self.env['withholding.tax.cert']
            certificates = WhtCert.search([('move_id', '=', self.id)])

            return {
                'type': 'ir.actions.act_window',
                'name': _('WHT Certificates'),
                'res_model': 'withholding.tax.cert',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', certificates.ids)],
                'target': 'current',
            }
        except Exception as e:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Error accessing WHT certificates: %s') % str(e),
                    'type': 'warning',
                }
            }

    def action_open_wht_clear_advance_wizard_from_bill(self):
        """Open WHT Clear Advance Wizard from vendor bill"""
        self.ensure_one()
        
        if self.move_type != 'in_invoice':
            raise UserError(_("This action is only available for vendor bills."))
        
        if self.state != 'posted':
            raise UserError(_("Bill must be posted before clearing with advance."))
        
        if self.amount_residual <= 0:
            raise UserError(_("Bill has no remaining balance to clear."))
        
        # Try to find related expense sheet
        expense_sheet = self.expense_sheet_id
        if not expense_sheet:
            # Search by various methods
            ExpenseSheet = self.env['hr.expense.sheet']
            if self.invoice_origin:
                expense_sheet = ExpenseSheet.search([('name', '=', self.invoice_origin)], limit=1)
            
            if not expense_sheet and self.ref:
                # Try to parse from reference
                if 'Expense Sheet' in self.ref:
                    sheet_name = self.ref.split('Expense Sheet', 1)[1].strip().lstrip(':').strip()
                    if sheet_name:
                        expense_sheet = ExpenseSheet.search([('name', 'ilike', sheet_name)], limit=1)
        
        if not expense_sheet:
            raise UserError(_("No related expense sheet found. This bill must be created from an expense sheet to use advance clearing."))
        
        # Get advance box - prioritize bill's advance_box_id, then expense_sheet's
        advance_box = self.advance_box_id or expense_sheet.advance_box_id
        if not advance_box:
            # Final fallback: search by employee
            advance_box = self.env['employee.advance.box'].search([
                ('employee_id', '=', expense_sheet.employee_id.id),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        
        if not advance_box:
            raise UserError(_("No advance box found. Please configure advance box for the employee %s in company %s.") % (expense_sheet.employee_id.name, self.company_id.name))
        
        # Get employee partner
        employee = expense_sheet.employee_id
        employee_partner = False
        if employee.user_id and employee.user_id.partner_id:
            employee_partner = employee.user_id.partner_id
        elif employee.address_home_id:
            employee_partner = employee.address_home_id
        
        # Check if the bill has WHT and if so, calculate the base amounts for each line
        has_wht = any(line.wht_tax_id for line in self.invoice_line_ids)
        if not has_wht:
            # Also check if any taxes are WHT taxes
            all_invoice_taxes = self.invoice_line_ids.mapped('tax_ids')
            has_wht = any(
                tax.amount < 0 and (hasattr(tax, 'l10n_th_is_withholding') and tax.l10n_th_is_withholding)
                for tax in all_invoice_taxes
            )
        
        base_amount = 0.0
        if has_wht:
            base_amount = self._get_wht_base_amount_excluding_vat()
        
        context = {
            'default_expense_sheet_id': expense_sheet.id,
            'default_employee_id': employee.id,
            'default_advance_box_id': advance_box.id,
            'default_company_id': self.company_id.id,
            'default_partner_id': self.partner_id.id,  # ใช้ vendor จาก bill แทน employee
            'default_wht_partner_id': self.partner_id.id,  # WHT partner ก็เป็น vendor เดียวกัน
            'default_clear_amount': self.amount_residual,
            'default_amount_base': base_amount if has_wht else self.amount_residual,
            'default_has_wht': has_wht,
        }
        
        _logger.info("DEBUG: Opening WHT wizard - Bill partner: %s (id: %s)", 
                     self.partner_id.name, self.partner_id.id)
        _logger.info("DEBUG: Expense sheet: %s, Advance box: %s (id: %s, balance: %s)", 
                     expense_sheet.name, advance_box.display_name, advance_box.id, advance_box.balance)
        _logger.info("DEBUG: WHT status - has_wht: %s, base_amount: %s", has_wht, base_amount)
        _logger.info("DEBUG: Full context being sent: %s", context)
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Clear Advance with WHT'),
            'res_model': 'wht.clear.advance.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': context,
        }
    
    def _get_wht_base_amount_excluding_vat(self):
        """Calculate total base amount excluding VAT for WHT calculation from all invoice lines"""
        total_base_amount = 0.0
        
        for line in self.invoice_line_ids:
            # Calculate the base amount for this line excluding VAT
            base_amount = self._get_base_amount_excluding_vat_for_line(line)
            total_base_amount += base_amount
            
        return total_base_amount

    def _get_base_amount_excluding_vat_for_line(self, invoice_line):
        """Calculate base amount excluding VAT for a specific invoice line for WHT calculation"""
        # Get the original line amount (total including tax)
        price_unit = invoice_line.price_unit
        quantity = invoice_line.quantity
        subtotal = price_unit * quantity

        # Get all VAT taxes (positive amount for purchases) - these are the taxes we need to exclude
        vat_taxes = invoice_line.tax_ids.filtered(lambda t: t.amount > 0)
        
        # If there are VAT taxes, we need to calculate the base amount before VAT
        if vat_taxes:
            # Use the same method Odoo uses to calculate the base amount before tax
            tax_compute_all = vat_taxes.compute_all(
                price_unit=price_unit,
                currency=invoice_line.currency_id,
                quantity=quantity,
                product=invoice_line.product_id,
                partner=invoice_line.partner_id
            )
            
            # The base amount is the amount before VAT was added
            base_amount = tax_compute_all['total_excluded']  # Amount before any taxes
        else:
            # If no VAT taxes, the base amount is just the subtotal
            base_amount = subtotal
            
        return base_amount
    
    def action_clear_advance_from_bill_smart(self):
        """Smart clearing method that automatically detects WHT and creates appropriate entries"""
        self.ensure_one()
        
        if self.move_type != 'in_invoice':
            raise UserError(_("This action is only available for vendor bills."))
        
        if self.state != 'posted':
            raise UserError(_("Bill must be posted before clearing with advance."))
        
        if self.amount_residual <= 0:
            raise UserError(_("Bill has no remaining balance to clear."))
        
        # Find related expense sheet
        ExpenseSheet = self.env['hr.expense.sheet']
        expense_sheet = self.expense_sheet_id or ExpenseSheet.search([('bill_id', '=', self.id)], limit=1)
        
        if not expense_sheet:
            # Search by other methods if not directly linked
            if self.invoice_origin:
                expense_sheet = ExpenseSheet.search([('name', '=', self.invoice_origin)], limit=1)
            
            if not expense_sheet and self.ref and 'Expense Sheet' in self.ref:
                sheet_name = self.ref.split('Expense Sheet', 1)[1].strip().lstrip(':').strip()
                if sheet_name:
                    expense_sheet = ExpenseSheet.search([('name', 'ilike', sheet_name)], limit=1)
        
        if not expense_sheet:
            raise UserError(_("No related expense sheet found. This bill must be created from an expense sheet to use advance clearing."))
        
        # Get advance box
        advance_box = self.advance_box_id or expense_sheet.advance_box_id
        if not advance_box:
            advance_box = self.env['employee.advance.box'].search([
                ('employee_id', '=', expense_sheet.employee_id.id),
                ('company_id', '=', self.company_id.id)
            ], limit=1)
        
        if not advance_box:
            raise UserError(_("No advance box found for employee %s.") % expense_sheet.employee_id.name)
        
        # Check if bill has WHT
        has_wht = any(line.wht_tax_id for line in self.invoice_line_ids)
        if not has_wht:
            # Also check if any taxes are WHT taxes
            all_invoice_taxes = self.invoice_line_ids.mapped('tax_ids')
            has_wht = any(
                tax.amount < 0 and (hasattr(tax, 'l10n_th_is_withholding') and tax.l10n_th_is_withholding)
                for tax in all_invoice_taxes
            )
        
        # Create the main clearing journal entry
        clearing_journal_id = self.env['ir.config_parameter'].sudo().get_param('employee_advance.advance_default_clearing_journal_id')
        if not clearing_journal_id:
            raise UserError(_('Please set the default clearing journal in configuration.'))
        
        journal = self.env['account.journal'].browse(int(clearing_journal_id))
        if not journal:
            raise UserError(_('Invalid clearing journal configured.'))
        
        # Get payable account from the bill
        payable_account = None
        for line in self.line_ids:
            if line.account_id.account_type == 'liability_payable' and line.balance < 0:
                payable_account = line.account_id
                break
        
        if not payable_account:
            raise UserError(_('Could not find payable account in the vendor bill.'))
        
        # Prepare main clearing entry - base amount for the clearing
        main_je_lines = [
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
        
        # If the bill has WHT, add WHT entries directly to main JE
        wht_amount_total = 0.0
        if has_wht:
            # Calculate total WHT amount for this bill based on base amounts excluding VAT
            wht_taxes = self.invoice_line_ids.filtered('wht_tax_id').mapped('wht_tax_id')
            wht_lines = self.invoice_line_ids.filtered(lambda l: l.wht_tax_id)
            
            for line in wht_lines:
                # Calculate base amount excluding VAT for this line
                base_amount = self._get_base_amount_excluding_vat_for_line(line)
                wht_amount = abs(base_amount * (line.wht_tax_id.amount / 100))
                wht_amount_total += wht_amount
                
                # Get WHT payable account
                wht_payable_account = None
                wht_tax_repartition = line.wht_tax_id.invoice_repartition_line_ids.filtered(
                    lambda r: r.repartition_type == 'tax' and r.account_id
                )
                if wht_tax_repartition:
                    wht_payable_account = wht_tax_repartition[0].account_id
                else:
                    # Fallback: look for common WHT payable account names
                    wht_payable_account = self.env['account.account'].search([
                        ('name', 'ilike', 'withholding'),
                        ('account_type', '=', 'liability_current'),
                        ('company_id', '=', self.company_id.id)
                    ], limit=1)
                
                if wht_payable_account:
                    # Add WHT payable line - increase the payable liability by the WHT amount
                    # This is because WHT reduces the vendor liability since we pay the tax instead of the vendor
                    main_je_lines.insert(0,  # Insert at beginning to maintain proper accounting structure
                        (0, 0, {
                            'account_id': payable_account.id,
                            'partner_id': self.partner_id.id,
                            'debit': wht_amount,
                            'credit': 0.0,
                            'name': f'WHT deduction on invoice line: {line.name}',
                        })
                    )
                    # Add WHT payable credit line
                    main_je_lines.append(
                        (0, 0, {
                            'account_id': wht_payable_account.id,
                            'partner_id': self.partner_id.id,  # Use bill partner for WHT certificate
                            'debit': 0.0,
                            'credit': wht_amount,
                            'name': f'WHT Payable - {line.wht_tax_id.name}',
                            'tax_line_id': line.wht_tax_id.id,
                            'tax_base_amount': base_amount,
                        })
                    )
        
        # Prepare the main JE
        je_vals = {
            'journal_id': journal.id,
            'company_id': journal.company_id.id if journal.company_id else self.company_id.id,
            'move_type': 'entry',
            'date': fields.Date.context_today(self),
            'ref': f'Clear Advance for {self.name}' + (f' (WHT: {wht_amount_total})' if has_wht else ''),
            'line_ids': main_je_lines
        }
        
        # Create and post the main clearing journal entry
        main_je = self.env['account.move'].create(je_vals)
        main_je.action_post()
        
        # Auto reconcile the advance clearing entry with the original bill
        original_payable_line = self.line_ids.filtered(
            lambda line: line.account_id.account_type == 'liability_payable' and line.balance < 0
        )[:1]
        
        # Find the corresponding payable line in the newly created JE
        je_payable_line = main_je.line_ids.filtered(
            lambda line: line.account_id.id == payable_account.id and line.debit > 0
        )[:1]
        
        if original_payable_line and je_payable_line:
            lines_to_reconcile = (original_payable_line + je_payable_line).sorted()
            if lines_to_reconcile and len(lines_to_reconcile.mapped('account_id')) == 1:
                try:
                    lines_to_reconcile.reconcile()
                except Exception as e:
                    _logger.warning(f"Could not reconcile advance clearing entry: {e}")
        
        # Log and refresh balance
        self.message_post(
            body=_("Advance cleared with journal entry %s. Dr %s, Cr %s. WHT processing: %s (Amount: %.2f)" %
                  (main_je.name, payable_account.code, advance_box.account_id.code, 
                   "Yes" if has_wht else "No", wht_amount_total))
        )
        
        try:
            advance_box._refresh_balance_simple()
            _logger.info("💰 Advance box balance refreshed after clearing")
        except Exception as e:
            _logger.warning("⚠️ Balance refresh failed after clearing, but operation succeeded: %s", str(e))
        
        # After main JE, make sure WHT certificates can be created
        if has_wht and wht_amount_total > 0:
            try:
                # Create WHT entries for tax tracking
                for line in wht_lines:
                    base_amount = self._get_base_amount_excluding_vat_for_line(line)
                    wht_amount = abs(base_amount * (line.wht_tax_id.amount / 100))
                    
                    self.env['account.withholding.move'].create({
                        'move_id': main_je.id,
                        'partner_id': self.partner_id.id,
                        'amount_income': base_amount,
                        'amount_wht': wht_amount,
                        'wht_tax_id': line.wht_tax_id.id,
                        'wht_cert_income_type': line.wht_tax_id.wht_cert_income_type or '5',
                        'company_id': self.company_id.id,
                    })
                
                # Try to create WHT certificates
                if hasattr(main_je, '_preapare_wht_certs'):
                    try:
                        main_je.create_wht_cert()
                    except:
                        _logger.info("WHT certificates created separately or not required")
            except Exception as e:
                _logger.warning(f"Could not create WHT tracking entries: {e}")
        
        return main_je

    def action_debug_wht_clear_conditions(self):
        """Debug method to show why WHT Clear button is not visible"""
        self.ensure_one()
        
        conditions = []
        
        # Check all conditions
        if self.move_type != 'in_invoice':
            conditions.append(f"❌ Move type: {self.move_type} (should be 'in_invoice')")
        else:
            conditions.append(f"✅ Move type: {self.move_type}")
        
        if self.state != 'posted':
            conditions.append(f"❌ State: {self.state} (should be 'posted')")
        else:
            conditions.append(f"✅ State: {self.state}")
            
        if self.amount_residual <= 0:
            conditions.append(f"❌ Amount residual: {self.amount_residual} (should be > 0)")
        else:
            conditions.append(f"✅ Amount residual: {self.amount_residual}")
            
        if not self.expense_sheet_id:
            conditions.append(f"❌ Expense sheet: Not linked")
        else:
            conditions.append(f"✅ Expense sheet: {self.expense_sheet_id.name}")
            
        if not self.advance_box_id:
            conditions.append(f"⚠️ Advance box: Not linked")
        else:
            conditions.append(f"✅ Advance box: {self.advance_box_id.display_name}")
        
        message = "WHT Clear Advance Button Visibility Check:\n\n" + "\n".join(conditions)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('WHT Clear Debug Info'),
                'message': message,
                'type': 'info',
                'sticky': True,
            }
        }


    def _auto_reconcile_wht_entries(self):
        """Auto reconcile WHT entries based on base amount excluding VAT"""
        self.ensure_one()
        
        if self.move_type != 'entry' or not self.line_ids:
            return False
        
        # Look for WHT lines in this journal entry
        wht_lines = self.line_ids.filtered(lambda l: l.tax_line_id and l.tax_line_id.amount < 0)
        
        if not wht_lines:
            # If no WHT tax lines, try to find lines that have WHT-related accounts
            wht_accounts = self.env['account.account'].search([
                ('name', 'ilike', '%withholding%'),
                ('company_id', '=', self.company_id.id)
            ])
            wht_lines = self.line_ids.filtered(lambda l: l.account_id in wht_accounts)
        
        if not wht_lines:
            return False
        
        # For each WHT line, try to find corresponding payable/receivable entries to reconcile
        reconciled_count = 0
        for wht_line in wht_lines:
            # Find payable lines with the same partner to reconcile against the WHT
            related_payable_lines = self.line_ids.filtered(
                lambda l: (l.partner_id.id == wht_line.partner_id.id and 
                          l.account_id.account_type == 'liability_payable' and 
                          l.id != wht_line.id)
            )
            
            for payable_line in related_payable_lines:
                try:
                    # For WHT, we typically reconcile the liability reduction (the payable line)
                    # against the payment or other journal entry lines
                    lines_to_reconcile = payable_line + wht_line
                    if lines_to_reconcile and len(lines_to_reconcile.mapped('account_id')) == 1:
                        lines_to_reconcile.reconcile()
                        reconciled_count += 1
                        _logger.info(f"WHT auto-reconciliation successful for lines in move {self.name}")
                        break  # Don't try to reconcile the same WHT line multiple times
                except Exception as e:
                    _logger.warning(f"Could not reconcile WHT line {wht_line.id} with payable {payable_line.id}: {str(e)}")
        
        return True

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    is_advance_clearing = fields.Boolean(string='Is Advance Clearing', default=False)
    reconciled_bill_ids = fields.One2many('account.move', 'payment_id', string='Reconciled Bills')
    
    # WHT Certificate count for smart button
    wht_cert_count = fields.Integer(
        string='WHT Certificate Count',
        compute='_compute_wht_cert_count'
    )

    @api.depends('line_ids')
    def _compute_wht_cert_count(self):
        """Compute the count of WHT certificates related to this payment"""
        for payment in self:
            count = 0
            try:
                # Check if WHT certificate module is installed
                if 'l10n.th.account.wht.cert.form' in self.env.registry:
                    WhtCert = self.env['l10n.th.account.wht.cert.form']
                    count = WhtCert.search_count([
                        '|',
                        ('move_id', '=', payment.move_id.id if payment.move_id else False),
                        ('move_line_ids', 'in', payment.line_ids.ids)
                    ])
            except Exception:
                count = 0
            payment.wht_cert_count = count

    def can_create_wht_certificate(self):
        """Check if WHT certificate can be created for this payment"""
        self.ensure_one()
        return (
            self.is_advance_clearing and 
            self.move_id and
            'l10n.th.account.wht.cert.form.wizard' in self.env.registry
        )

    def action_view_wht_certificates(self):
        """View related WHT certificates for this payment"""
        self.ensure_one()
        
        try:
            if 'l10n.th.account.wht.cert.form' not in self.env.registry:
                raise UserError(_("Thai WHT Certificate module is not installed."))
            WhtCert = self.env['l10n.th.account.wht.cert.form']
        except Exception:
            return

        certificates = WhtCert.search([
            '|',
            ('move_id', '=', self.move_id.id if self.move_id else False),
            ('move_line_ids', 'in', self.line_ids.ids)
        ])

        return {
            'type': 'ir.actions.act_window',
            'name': _('WHT Certificates'),
            'res_model': 'l10n.th.account.wht.cert.form',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', certificates.ids)],
            'target': 'current',
        }
