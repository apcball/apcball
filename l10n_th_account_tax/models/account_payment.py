# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (http    def _compute_wht_cert_count(self)://www.gnu.org/licenses/agpl.html)
import logging
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    to_clear_tax = fields.Boolean(
        default=False,
        copy=False,
        help="When defer journal entry posting, this will show button",
    )
    tax_invoice_ids = fields.One2many(
        comodel_name="account.move.tax.invoice",
        inverse_name="payment_id",
        copy=False,
        domain=[("reversing_id", "=", False), ("reversed_id", "=", False)],
    )
    tax_invoice_move_ids = fields.Many2many(
        comodel_name="account.move",
        relation="payment_tax_invoice_rel",
        column1="payment_id",
        column2="tax_invoice_id",
        string="Tax Invoice's Journal Entry",
        compute="_compute_tax_invoice_move_ids",
    )
    wht_move_ids = fields.One2many(
        comodel_name="account.withholding.move",
        inverse_name="payment_id",
        string="Withholding",
        copy=False,
        help="All withholding moves, including non-PIT",
    )
    pit_move_ids = fields.One2many(
        comodel_name="account.withholding.move",
        inverse_name="payment_id",
        string="Personal Income Tax",
        domain=[("is_pit", "=", True)],
        copy=False,
    )
    wht_cert_ids = fields.One2many(
        comodel_name="withholding.tax.cert",
        inverse_name="payment_id",
        string="Withholding Tax Cert.",
        readonly=True,
    )
    wht_certs_count = fields.Integer(
        string="# Withholding Tax Certs",
        compute="_compute_wht_certs_count",
    )
    
    # Enhanced WHT Certificate fields
    wht_cert_count = fields.Integer(
        string='WHT Certificates Count',
        compute='_compute_wht_cert_count'
    )
    wht_tax_amount = fields.Monetary(
        string='WHT Tax Amount',
        currency_field='currency_id',
        help='Amount of withholding tax deducted from this payment'
    )
    # Keep only essential fields from original module
    wht_tax_rate = fields.Float(
        string='WHT Tax Rate (%)',
        help='Withholding tax rate percentage'
    )
    wht_base_amount = fields.Monetary(
        string='WHT Base Amount',
        currency_field='currency_id',
        help='Base amount for withholding tax calculation'
    )

    def _compute_wht_certs_count(self):
        for payment in self:
            payment.wht_certs_count = len(payment.wht_cert_ids)
    
    def _compute_wht_cert_count(self):
        for payment in self:
            payment.wht_cert_count = len(payment.wht_cert_ids)

    def _compute_has_wht_tax(self):
        for payment in self:
            has_wht = False
            
            # Check from reconciled bills/invoices
            if payment.reconciled_bill_ids:
                if any(bill.total_withholding_tax > 0 for bill in payment.reconciled_bill_ids):
                    has_wht = True
            
            # Check from manual WHT amount
            elif payment.wht_tax_amount > 0:
                has_wht = True
            
            # Check from wht_move_ids
            elif payment.wht_move_ids:
                has_wht = True
            
            # Check from journal entry
            elif payment.move_id:
                # Look for typical WHT patterns in journal lines
                for line in payment.move_id.line_ids:
                    account_name = line.account_id.name.lower()
                    account_code = line.account_id.code or ''
                    
                    wht_patterns = [
                        'withholding', 'หัก ณ ที่จ่าย', 'wht', 'ภาษีหัก',
                        '1512', '15120', '151200'  # Common WHT account codes
                    ]
                    
                    if (any(pattern in account_name for pattern in wht_patterns[:4]) or 
                        any(pattern in account_code for pattern in wht_patterns[4:])):
                        if line.debit > 0:  # WHT is usually a debit
                            has_wht = True
                            break
            
            payment.has_wht_tax = has_wht

    def _compute_withholding_totals(self):
        for payment in self:
            total_base = 0.0
            total_tax = 0.0
            
            # Method 1: From reconciled bills/invoices
            if payment.reconciled_bill_ids:
                total_base = sum(payment.reconciled_bill_ids.mapped('total_withholding_base'))
                total_tax = sum(payment.reconciled_bill_ids.mapped('total_withholding_tax'))
            
            # Method 2: From manual fields
            elif payment.wht_tax_amount > 0 and payment.wht_base_amount > 0:
                total_base = payment.wht_base_amount
                total_tax = payment.wht_tax_amount
            
            # Method 3: From wht_move_ids
            elif payment.wht_move_ids:
                total_base = sum(payment.wht_move_ids.mapped('amount_income'))
                total_tax = sum(payment.wht_move_ids.mapped('amount_wht'))
            
            # Method 4: From journal entry lines
            elif payment.move_id:
                wht_lines = payment.move_id.line_ids.filtered(
                    lambda l: l.debit > 0 and l.account_id.id != payment.destination_account_id.id
                )
                
                for line in wht_lines:
                    account_name = line.account_id.name.lower()
                    account_code = line.account_id.code or ''
                    
                    wht_patterns = ['withholding', 'หัก ณ ที่จ่าย', 'wht', 'ภาษีหัก']
                    wht_codes = ['1512', '15120', '151200']
                    
                    if (any(pattern in account_name for pattern in wht_patterns) or 
                        any(code in account_code for code in wht_codes)):
                        total_tax += line.debit
                        # Estimate base (assuming 3% WHT rate if no tax_line_id)
                        if line.tax_line_id and line.tax_line_id.amount > 0:
                            total_base += (line.debit * 100) / abs(line.tax_line_id.amount)
                        else:
                            total_base += (line.debit * 100) / 3  # Default 3% assumption
            
            payment.total_withholding_base = total_base
            payment.total_withholding_tax = total_tax

    # Remove unused methods - clean up payment model

    def button_wht_certs(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "l10n_th_account_tax.action_withholding_tax_cert_menu"
        )
        action["domain"] = [("id", "in", self.wht_cert_ids.ids)]
        return action

    def clear_tax_cash_basis(self):
        for payment in self:
            # Debug: Check if there are any tax invoice lines
            if not payment.tax_invoice_ids:
                # No tax invoices to process, just clear the flag
                payment.write({"to_clear_tax": False})
                continue
                
            # Check each tax invoice line for required fields
            missing_invoices = []
            for tax_invoice in payment.tax_invoice_ids:
                missing_fields = []
                
                # Debug information
                _logger = logging.getLogger(__name__)
                _logger.info(f"Checking tax invoice {tax_invoice.id}: number='{tax_invoice.tax_invoice_number}', date='{tax_invoice.tax_invoice_date}'")
                
                if not tax_invoice.tax_invoice_number or tax_invoice.tax_invoice_number.strip() == '':
                    missing_fields.append("Tax Invoice Number")
                if not tax_invoice.tax_invoice_date:
                    missing_fields.append("Tax Invoice Date")
                
                if missing_fields:
                    missing_invoices.append(f"Tax Invoice Line {tax_invoice.id}: {', '.join(missing_fields)}")
            
            # If any invoices are missing required fields, show detailed error
            if missing_invoices:
                error_msg = _("Please fill in the following required fields:\n\n%s\n\nNote: Make sure all fields are properly saved before clicking this button.") % '\n'.join(missing_invoices)
                raise UserError(error_msg)
                
            payment.write({"to_clear_tax": False})
            moves = payment.tax_invoice_ids.mapped("move_id")
            for move in moves:
                if move.state != "draft":
                    continue
                move.action_post()
                # Reconcile Case Basis
                line = move.line_ids.filtered(
                    lambda l: l.id
                    not in payment.tax_invoice_ids.mapped("move_line_id").ids
                )
                if line.account_id.reconcile:
                    origin_ml = move.tax_cash_basis_origin_move_id.line_ids
                    counterpart_line = origin_ml.filtered(
                        lambda l: l.account_id.id == line.account_id.id
                    )
                    (line + counterpart_line).reconcile()
        return True

    def _compute_tax_invoice_move_ids(self):
        for payment in self:
            payment.tax_invoice_move_ids = payment.tax_invoice_ids.mapped("move_id")

    def button_open_journal_entry(self):
        """Add tax cash basis when open journal entry"""
        self.ensure_one()
        if self.tax_invoice_move_ids:
            moves = self.tax_invoice_move_ids + self.move_id
            return {
                "name": _("Journal Entry"),
                "type": "ir.actions.act_window",
                "res_model": "account.move",
                "context": {"create": False},
                "view_mode": "tree,form",
                "domain": [("id", "in", moves.ids)],
            }
        return super().button_open_journal_entry()

    def create_wht_cert(self):
        self.ensure_one()
        self.move_id.create_wht_cert()



    def action_view_wht_certificates(self):
        """Action to view WHT certificates"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "l10n_th_account_tax.action_withholding_tax_cert_menu"
        )
        action["domain"] = [("id", "in", self.wht_cert_ids.ids)]
        action["context"] = {"default_payment_id": self.id}
        return action

    def action_post(self):
        """Override to auto-generate WHT certificates after posting"""
        res = super().action_post()
        
        # Auto-generate WHT certificates if payment has WHT
        for payment in self:
            if payment.wht_move_ids and payment.state == 'posted':
                try:
                    # Try to generate certificates via the move
                    if payment.move_id:
                        payment.move_id.auto_create_wht_cert_from_payment()
                    else:
                        # Fallback to payment method
                        payment._auto_generate_wht_certificates()
                except Exception as e:
                    _logger = logging.getLogger(__name__)
                    _logger.warning(f"Failed to auto-generate WHT certificate for payment {payment.name}: {e}")
        
        return res

    # Remove all unused WHT generation methods - use invoice wizard instead

    def _compute_tax_invoice_move_ids(self):        return res

    def action_manual_generate_wht_cert(self):
        """สร้าง WHT Certificate แบบแมนนวล"""
        try:
            # Recompute fields
            self._compute_withholding_totals()
            
            # Check conditions
            if not self.total_withholding_tax:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': 'ไม่พบข้อมูลภาษี WHT ในการชำระเงินนี้',
                        'type': 'warning',
                        'sticky': False,
                    }
                }
            
            # Try to create certificate automatically
            cert = self._generate_wht_cert_from_totals()
            if cert:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'message': f'สร้าง WHT Certificate สำเร็จ: {cert.name}',
                        'type': 'success',
                        'sticky': False,
                    }
                }
            
            # Fallback to wizard
            return {
                'type': 'ir.actions.act_window',
                'name': 'สร้าง WHT Certificate',
                'res_model': 'wht.manual.create.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_payment_id': self.id,
                    'default_partner_id': self.partner_id.id,
                    'default_total_base': self.total_withholding_base,
                    'default_total_tax': self.total_withholding_tax,
                }
            }
            
        except Exception:
            # Any error - fallback to wizard
            return {
                'type': 'ir.actions.act_window',
                'name': 'สร้าง WHT Certificate',
                'res_model': 'wht.manual.create.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_payment_id': self.id,
                    'default_partner_id': self.partner_id.id,
                    'default_total_base': 0.0,
                    'default_total_tax': 0.0,
                }
            }

    def action_view_wht_certificates(self):
        """Action to view WHT certificates"""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "l10n_th_account_tax.action_withholding_tax_cert_menu"
        )
        action["domain"] = [("id", "in", self.wht_cert_ids.ids)]
        action["context"] = {"default_payment_id": self.id}
        return action

    def action_manual_generate_wht_cert(self):
        """Manual action to generate WHT certificate - safe version"""
        self.ensure_one()
        
        try:
            # Check if certificates already exist
            if self.wht_cert_ids:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Warning'),
                        'message': _('WHT certificates already exist for this payment.'),
                        'type': 'warning',
                    }
                }
            
            # Simple check for WHT data
            has_wht_data = (
                self.total_withholding_tax > 0 or 
                self.wht_tax_amount > 0 or 
                bool(self.wht_move_ids)
            )
            
            if not has_wht_data:
                # Open wizard for manual creation
                return {
                    'type': 'ir.actions.act_window',
                    'res_model': 'wht.manual.create.wizard',
                    'view_mode': 'form',
                    'view_type': 'form',
                    'target': 'new',
                    'context': {
                        'default_payment_id': self.id,
                        'default_partner_id': self.partner_id.id,
                        'default_amount_total': self.amount,
                    }
                }
            
            # Generate certificate using existing data
            cert = None
            if self.wht_move_ids:
                certs = self._auto_generate_wht_certificates()
                cert = certs[0] if certs else None
            elif self.total_withholding_tax > 0:
                cert = self._generate_wht_cert_from_totals()
            
            if cert:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Success'),
                        'message': _('WHT Certificate %s generated successfully!') % cert.name,
                        'type': 'success',
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Error'),
                        'message': _('Could not generate WHT certificate. Please check the data.'),
                        'type': 'danger',
                    }
                }
                
        except Exception as e:
            # Log the error but don't break the transaction
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error in manual WHT cert generation: {e}")
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Error'),
                    'message': _('Failed to generate certificate. Please try again or contact administrator.'),
                    'type': 'danger',
                }
            }

    def _generate_wht_cert_from_totals(self):
        """Generate WHT certificate from total withholding amounts"""
        self.ensure_one()
        
        if not self.total_withholding_tax or not self.total_withholding_base:
            raise UserError(_('No withholding tax amounts found to generate certificate.'))
        
        # Get partner from payment
        partner = self.partner_id
        if not partner:
            raise UserError(_('No partner found for this payment.'))
        
        # Create certificate
        cert_vals = {
            'partner_id': partner.id,
            'payment_id': self.id,
            'date': self.date,
            'state': 'draft',
            'company_partner_id': self.company_id.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'income_tax_form': 'pnd3',  # Default
        }
        
        try:
            cert = self.env['withholding.tax.cert'].create(cert_vals)
            
            # Create certificate line
            line_vals = {
                'cert_id': cert.id,
                'base': self.total_withholding_base,
                'amount': self.total_withholding_tax,
                'wht_cert_income_type': '5',  # Default: ค่าจ้างทำของ ค่าบริการ
            }
            
            # Try to find a WHT tax for this line
            if self.reconciled_bill_ids:
                for bill in self.reconciled_bill_ids:
                    wht_tax_lines = bill.line_ids.filtered(
                        lambda l: l.tax_line_id and (
                            l.tax_line_id.amount < 0 or 
                            'withholding' in l.tax_line_id.name.lower() or 
                            'หัก' in l.tax_line_id.name
                        )
                    )
                    if wht_tax_lines:
                        line_vals['wht_tax_id'] = wht_tax_lines[0].tax_line_id.id
                        break
            
            cert_line = self.env['withholding.tax.cert.line'].create(line_vals)
            
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Created WHT certificate {cert.name} from totals for payment {self.name}")
            return cert
            
        except Exception as e:
            import logging
            _logger = logging.getLogger(__name__)
            _logger.error(f"Error creating WHT certificate: {e}")
            raise UserError(_('Failed to create WHT certificate: %s') % str(e))

    def _generate_wht_cert_from_journal_lines(self):
        """Generate WHT certificate from journal entry lines when no wht_move_ids"""
        self.ensure_one()
        
        if not self.move_id:
            return False
        
        # Find WHT tax lines
        wht_taxes = self.env['account.tax'].search([
            '|', '|',
            ('name', 'ilike', 'withholding'),
            ('name', 'ilike', 'หัก ณ ที่จ่าย'),
            ('description', 'ilike', 'wht'),
            ('company_id', '=', self.company_id.id)
        ])
        
        wht_lines = self.move_id.line_ids.filtered(
            lambda l: l.tax_line_id.id in wht_taxes.ids and l.debit > 0
        )
        
        if not wht_lines:
            # Try to find by account name/code
            wht_accounts = self.env['account.account'].search([
                '|',
                ('name', 'ilike', 'withholding'),
                ('code', 'like', '%หัก%'),
                ('company_id', '=', self.company_id.id)
            ])
            wht_lines = self.move_id.line_ids.filtered(
                lambda l: l.account_id.id in wht_accounts.ids and l.debit > 0
            )
        
        if not wht_lines:
            raise UserError(_('No withholding tax lines found in payment journal entry.'))
        
        # Get partner from payment
        partner = self.partner_id
        if not partner:
            raise UserError(_('No partner found for this payment.'))
        
        # Calculate totals from WHT lines
        total_wht = sum(line.debit for line in wht_lines)
        
        # Estimate base amount (assuming standard WHT rates)
        estimated_base = 0
        for line in wht_lines:
            if line.tax_line_id and line.tax_line_id.amount > 0:
                # Calculate base from tax amount and rate
                estimated_base += (line.debit * 100) / abs(line.tax_line_id.amount)
            else:
                # Default assumption: 3% WHT rate
                estimated_base += (line.debit * 100) / 3
        
        # Create certificate
        cert_vals = {
            'partner_id': partner.id,
            'payment_id': self.id,
            'date': self.date,
            'state': 'draft',
            'company_partner_id': self.company_id.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'income_tax_form': 'pnd3',  # Default
        }
        
        cert = self.env['withholding.tax.cert'].create(cert_vals)
        
        # Create certificate lines
        for wht_line in wht_lines:
            # Calculate base for this line
            if wht_line.tax_line_id and wht_line.tax_line_id.amount > 0:
                line_base = (wht_line.debit * 100) / abs(wht_line.tax_line_id.amount)
            else:
                line_base = (wht_line.debit * 100) / 3  # Default 3% assumption
            
            line_vals = {
                'cert_id': cert.id,
                'base': line_base,
                'amount': wht_line.debit,
                'wht_cert_income_type': '5',  # Default: ค่าจ้างทำของ ค่าบริการ
            }
            
            if wht_line.tax_line_id:
                line_vals['wht_tax_id'] = wht_line.tax_line_id.id
            
            self.env['withholding.tax.cert.line'].create(line_vals)
        
        _logger = logging.getLogger(__name__)
        _logger.info(f"Created WHT certificate {cert.name} from journal lines for payment {self.name}")
        return cert

    def _auto_generate_wht_certificates(self):
        """Auto-generate WHT certificates from withholding moves"""
        self.ensure_one()
        
        if not self.wht_move_ids:
            return False
        
        # Group withholding moves by partner
        partner_wht_data = {}
        for wht_move in self.wht_move_ids:
            partner_id = wht_move.partner_id.id
            if partner_id not in partner_wht_data:
                partner_wht_data[partner_id] = []
            partner_wht_data[partner_id].append(wht_move)
        
        # Create certificates for each partner
        created_certs = []
        for partner_id, wht_moves in partner_wht_data.items():
            partner = self.env['res.partner'].browse(partner_id)
            cert = self._create_wht_certificate_from_moves(partner, wht_moves)
            if cert:
                created_certs.append(cert)
        
        return created_certs

    def _create_wht_certificate_from_moves(self, partner, wht_moves):
        """Create WHT certificate from withholding moves"""
        
        # Calculate totals
        total_base = sum(move.amount_income for move in wht_moves)
        total_wht = sum(move.amount_wht for move in wht_moves)
        
        # Get the first tax for default form
        first_tax = None
        if wht_moves and wht_moves[0].wht_tax_id:
            first_tax = wht_moves[0].wht_tax_id
        
        # Create certificate
        cert_vals = {
            'partner_id': partner.id,
            'payment_id': self.id,
            'date': self.date,
            'state': 'draft',
            'company_partner_id': self.company_id.partner_id.id,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
        }
        
        # Set default income tax form
        if first_tax and hasattr(first_tax, 'income_tax_form'):
            cert_vals['income_tax_form'] = first_tax.income_tax_form
        else:
            cert_vals['income_tax_form'] = 'pnd3'  # Default
        
        try:
            cert = self.env['withholding.tax.cert'].create(cert_vals)
            
            # Create certificate lines
            for wht_move in wht_moves:
                line_vals = {
                    'cert_id': cert.id,
                    'base': wht_move.amount_income,
                    'amount': wht_move.amount_wht,
                }
                
                # Set income type
                if wht_move.wht_cert_income_type:
                    line_vals['wht_cert_income_type'] = wht_move.wht_cert_income_type
                else:
                    line_vals['wht_cert_income_type'] = '5'  # Default: ค่าจ้างทำของ ค่าบริการ
                
                # Set withholding tax
                if wht_move.wht_tax_id:
                    line_vals['wht_tax_id'] = wht_move.wht_tax_id.id
                
                self.env['withholding.tax.cert.line'].create(line_vals)
                
                # Link the cert to the withholding move
                wht_move.cert_id = cert.id
            
            _logger = logging.getLogger(__name__)
            _logger.info(f"Created WHT certificate {cert.name} for payment {self.name} with partner {partner.name}")
            return cert
            
        except Exception as e:
            _logger = logging.getLogger(__name__)
            _logger.error(f"Failed to create WHT certificate: {e}")
            raise


