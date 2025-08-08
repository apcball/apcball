# Copyright 2024 Ecosoft Co., Ltd (https://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo import api, fields, models, Command, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class AccountPayment(models.Model):
    _inherit = "account.payment"
    
    # WHT Certificate fields
    wht_cert_ids = fields.One2many(
        'withholding.tax.cert',
        'payment_id',
        string='WHT Certificates',
        help='Auto-generated WHT Certificates for this payment'
    )
    
    wht_cert_count = fields.Integer(
        string='WHT Certificates Count',
        compute='_compute_wht_cert_count'
    )
    
    has_wht_tax = fields.Boolean(
        string='Has WHT Tax',
        compute='_compute_has_wht_tax',
        store=True,
        help='True if this payment has withholding tax'
    )
    
    @api.depends('wht_cert_ids')
    def _compute_wht_cert_count(self):
        for payment in self:
            payment.wht_cert_count = len(payment.wht_cert_ids)
    
    @api.depends('reconciled_invoice_ids', 'reconciled_bill_ids', 'move_id.line_ids.tax_ids')
    def _compute_has_wht_tax(self):
        """Check if payment involves WHT tax"""
        for payment in self:
            has_wht = False
            
            # Check reconciled bills and invoices for WHT taxes
            all_invoices = payment.reconciled_bill_ids + payment.reconciled_invoice_ids
            for invoice in all_invoices:
                # Check for negative taxes (WHT taxes)
                for line in invoice.invoice_line_ids:
                    wht_taxes = line.tax_ids.filtered(lambda t: t.amount < 0)
                    if wht_taxes:
                        has_wht = True
                        break
                
                # Also check existing wht_tax_id field from current system
                if hasattr(invoice, 'line_ids'):
                    wht_lines = invoice.line_ids.filtered(lambda l: l.wht_tax_id)
                    if wht_lines:
                        has_wht = True
                        break
                        
                if has_wht:
                    break
            
            payment.has_wht_tax = has_wht    def action_post(self):
        """Override to auto-generate WHT certificates after posting payment"""
        res = super().action_post()
        
        # Auto-generate WHT certificates for payments with WHT tax
        for payment in self:
            if payment.has_wht_tax and not payment.wht_cert_ids:
                try:
                    payment._auto_generate_wht_certificates()
                    _logger.info(f"Auto-generated WHT certificate for payment {payment.name}")
                except Exception as e:
                    _logger.warning(f"Failed to auto-generate WHT certificate for payment {payment.name}: {e}")
        
        return res
    
    def _auto_generate_wht_certificates(self):
        """Auto-generate WHT certificates based on payment WHT taxes"""
        self.ensure_one()
        
        if not self.has_wht_tax:
            return
        
        _logger.info(f"Auto-generating WHT certificates for payment {self.name}")
        
        # Get WHT tax information from reconciled invoices
        wht_data = self._get_wht_tax_data()
        
        if not wht_data:
            return
        
        # Group by partner and create certificates
        partner_wht_data = {}
        for data in wht_data:
            partner_id = data['partner_id']
            if partner_id not in partner_wht_data:
                partner_wht_data[partner_id] = []
            partner_wht_data[partner_id].append(data)
        
        # Create certificates for each partner
        for partner_id, partner_data in partner_wht_data.items():
            partner = self.env['res.partner'].browse(partner_id)
            self._create_wht_certificate(partner, partner_data)
    
    def _get_wht_tax_data(self):
        """Extract WHT tax data from reconciled invoices"""
        wht_data = []
        
        # Check both bill and invoice types
        all_invoices = self.reconciled_bill_ids + self.reconciled_invoice_ids
        
        for invoice in all_invoices:
            # Method 1: Check current system wht_tax_id field
            for line in invoice.line_ids:
                if hasattr(line, 'wht_tax_id') and line.wht_tax_id:
                    wht_tax = line.wht_tax_id
                    
                    # Calculate amounts from line
                    if invoice.move_type in ('in_invoice', 'in_refund'):
                        base_amount = abs(line.debit or line.credit)
                        wht_amount = abs(base_amount * (wht_tax.percent / 100))
                    else:
                        base_amount = abs(line.credit or line.debit)  
                        wht_amount = abs(base_amount * (wht_tax.percent / 100))
                    
                    wht_data.append({
                        'partner_id': invoice.partner_id.id,
                        'tax_id': wht_tax.id,
                        'tax_name': wht_tax.name,
                        'base_amount': base_amount,
                        'wht_amount': wht_amount,
                        'income_type': self._get_income_type_from_wht_tax(wht_tax),
                        'invoice_id': invoice.id,
                        'line_id': line.id,
                    })
            
            # Method 2: Check standard tax_ids with negative amounts
            for line in invoice.invoice_line_ids:
                wht_taxes = line.tax_ids.filtered(lambda t: t.amount < 0)
                
                for tax in wht_taxes:
                    base_amount = line.price_subtotal
                    wht_amount = abs(base_amount * (tax.amount / 100))
                    
                    wht_data.append({
                        'partner_id': invoice.partner_id.id,
                        'tax_id': tax.id,
                        'tax_name': tax.name,
                        'base_amount': base_amount,
                        'wht_amount': wht_amount,
                        'income_type': self._get_income_type_from_tax_name(tax.name),
                        'invoice_id': invoice.id,
                        'line_id': line.id,
                    })
        
        return wht_data
    
    def _get_income_type_from_wht_tax(self, wht_tax):
        """Determine income type from withholding tax record"""
        if hasattr(wht_tax, 'income_type'):
            return wht_tax.income_type
        
        # Fallback to name parsing
        return self._get_income_type_from_tax_name(wht_tax.name)
    
    def _get_income_type_from_tax_name(self, tax_name):
        """Determine income type from tax name"""
        tax_name = tax_name.lower()
        
        if 'service' in tax_name:
            return 'service'
        elif 'rental' in tax_name or 'rent' in tax_name:
            return 'rental'
        elif 'professional' in tax_name:
            return 'professional'
        elif 'transport' in tax_name:
            return 'transport'
        else:
            return 'other'
    
    def _get_income_type_from_tax(self, tax):
        """Determine income type from tax name/tags - Legacy method"""
        return self._get_income_type_from_tax_name(tax.name)
    
    def _create_wht_certificate(self, partner, wht_data):
        """Create WHT certificate for a partner using current system"""
        
        # Calculate totals
        total_base = sum(data['base_amount'] for data in wht_data)
        total_wht = sum(data['wht_amount'] for data in wht_data)
        
        # Create certificate using current system structure
        cert_vals = {
            'partner_id': partner.id,
            'payment_id': self.id,
            'date': self.date,
            'state': 'draft',
            'income_tax_form': 'pnd3',  # Default form
            'company_partner_id': self.company_id.partner_id.id,
            'total_amount': total_wht,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
        }
        
        # Auto-generate certificate number if not exists
        if not cert_vals.get('number'):
            cert_vals['number'] = self._generate_wht_cert_number()
        
        try:
            cert = self.env['withholding.tax.cert'].create(cert_vals)
            _logger.info(f"Created WHT certificate {cert.number} for payment {self.name} with partner {partner.name}")
            return cert
        except Exception as e:
            _logger.error(f"Failed to create WHT certificate: {e}")
            # Create simplified certificate
            simple_cert_vals = {
                'partner_id': partner.id,
                'payment_id': self.id,
                'date': self.date,
                'state': 'draft',
                'total_amount': total_wht,
            }
            cert = self.env['withholding.tax.cert'].create(simple_cert_vals)
            _logger.info(f"Created simplified WHT certificate for payment {self.name}")
            return cert
    
    def _get_wht_tax_cert_id(self, payment_tax_id):
        """Get corresponding withholding tax cert record for payment tax"""
        # Map payment tax to withholding tax cert
        payment_tax = self.env['account.tax'].browse(payment_tax_id)
        
        # Find matching withholding tax based on name/amount
        wht_tax = self.env['account.withholding.tax'].search([
            ('name', 'ilike', payment_tax.name.replace('WHT', '').strip()),
            ('amount', '=', abs(payment_tax.amount))
        ], limit=1)
        
        return wht_tax.id if wht_tax else False
    
    def _generate_wht_cert_number(self):
        """Generate WHT certificate number"""
        # Use sequence or simple numbering
        year = fields.Date.today().year
        sequence = self.env['ir.sequence'].next_by_code('wht.cert.auto') or '001'
        return f"WHT-{year}-{sequence}"
    
    def action_manual_generate_wht_cert(self):
        """Manual WHT certificate generation for testing"""
        self.ensure_one()
        if self.has_wht_tax:
            try:
                self._auto_generate_wht_certificates()
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Success',
                        'message': 'WHT Certificate generated successfully!',
                        'type': 'success',
                    }
                }
            except Exception as e:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': 'Error',
                        'message': f'Failed to generate WHT Certificate: {str(e)}',
                        'type': 'danger',
                    }
                }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Warning',
                    'message': 'This payment does not contain WHT tax.',
                    'type': 'warning',
                }
            }

    def action_view_wht_certificates(self):
        """View WHT certificates linked to this payment"""
        self.ensure_one()
        if len(self.wht_cert_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': 'WHT Certificate',
                'res_model': 'withholding.tax.cert',
                'res_id': self.wht_cert_ids[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': 'WHT Certificates',
                'res_model': 'withholding.tax.cert',
                'domain': [('payment_id', '=', self.id)],
                'view_mode': 'tree,form',
                'target': 'current',
            }
        """Open WHT certificates related to this payment"""
        self.ensure_one()
        
        if len(self.wht_cert_ids) == 1:
            return {
                'type': 'ir.actions.act_window',
                'name': 'WHT Certificate',
                'res_model': 'withholding.tax.cert',
                'res_id': self.wht_cert_ids[0].id,
                'view_mode': 'form',
                'target': 'current',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': 'WHT Certificates',
                'res_model': 'withholding.tax.cert',
                'domain': [('id', 'in', self.wht_cert_ids.ids)],
                'view_mode': 'tree,form',
                'target': 'current',
            }
    
    def action_manual_generate_wht_cert(self):
        """Manual action to generate WHT certificate"""
        self.ensure_one()
        
        if not self.has_wht_tax:
            raise UserError(_("This payment does not have withholding tax."))
        
        if self.wht_cert_ids:
            raise UserError(_("WHT certificates already exist for this payment."))
        
        self._auto_generate_wht_certificates()
        
        return self.action_view_wht_certificates()


class WithholdingTaxCert(models.Model):
    _inherit = "withholding.tax.cert"
    
    payment_id = fields.Many2one(
        'account.payment',
        string='Payment',
        help='Payment that generated this certificate'
    )
    
    auto_generated = fields.Boolean(
        string='Auto Generated',
        default=False,
        help='True if this certificate was auto-generated from payment'
    )
