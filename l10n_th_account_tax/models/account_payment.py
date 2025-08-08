# Copyright 2019 Ecosoft Co., Ltd (http://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
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

    @api.depends("wht_cert_ids")
    def _compute_wht_certs_count(self):
        for payment in self:
            payment.wht_certs_count = len(payment.wht_cert_ids)

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

    @api.depends("tax_invoice_ids")
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

    # New WHT System v2.0 Fields and Methods
    has_wht_tax = fields.Boolean(
        string='Has WHT Tax',
        compute='_compute_has_wht_tax',
        help='Indicates if this payment involves withholding tax',
    )
    
    wht_cert_count = fields.Integer(
        string='WHT Certificate Count',
        compute='_compute_wht_cert_count',
        help='Number of WHT certificates linked to this payment'
    )

    @api.depends('reconciled_bill_ids', 'reconciled_invoice_ids')
    def _compute_has_wht_tax(self):
        """Check if payment involves WHT tax"""
        for payment in self:
            wht_found = False
            # Check bills and invoices for WHT taxes
            all_invoices = payment.reconciled_bill_ids + payment.reconciled_invoice_ids
            for invoice in all_invoices:
                # Check for wht_tax_id field
                if invoice.line_ids.filtered(lambda l: hasattr(l, 'wht_tax_id') and l.wht_tax_id):
                    wht_found = True
                    break
                # Check for standard tax lines with negative amounts (WHT)
                if invoice.line_ids.filtered(lambda l: l.tax_line_id and l.tax_line_id.amount < 0):
                    wht_found = True
                    break
                # Check for invoice lines with WHT taxes
                for line in invoice.invoice_line_ids or []:
                    if line.tax_ids.filtered(lambda t: t.amount < 0):
                        wht_found = True
                        break
                if wht_found:
                    break
            payment.has_wht_tax = wht_found

    @api.depends('wht_cert_ids')
    def _compute_wht_cert_count(self):
        """Count WHT certificates"""
        for payment in self:
            payment.wht_cert_count = len(payment.wht_cert_ids)

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
            if payment.has_wht_tax and payment.state == 'posted':
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

    def action_manual_generate_wht_cert(self):
        """Manual WHT certificate generation"""
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

    def _auto_generate_wht_certificates(self):
        """Auto-generate WHT certificates for payment"""
        self.ensure_one()
        
        # Get WHT data from reconciled invoices
        wht_data = self._get_wht_tax_data()
        if not wht_data:
            return
        
        # Group by partner
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
                        'invoice_id': invoice.id,
                        'line_id': line.id,
                    })
            
            # Method 2: Check standard tax lines with negative amounts (WHT)
            for line in invoice.line_ids:
                if line.tax_line_id and line.tax_line_id.amount < 0:
                    # This is a WHT tax line
                    wht_tax = line.tax_line_id
                    base_amount = abs(line.tax_base_amount)
                    wht_amount = abs(line.balance)
                    
                    wht_data.append({
                        'partner_id': invoice.partner_id.id,
                        'tax_id': wht_tax.id,
                        'tax_name': wht_tax.name,
                        'base_amount': base_amount,
                        'wht_amount': wht_amount,
                        'invoice_id': invoice.id,
                        'line_id': line.id,
                    })
        
        return wht_data

    def _create_wht_certificate(self, partner, wht_data):
        """Create WHT certificate for a partner using current system"""
        
        # Calculate totals
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
        
        try:
            cert = self.env['withholding.tax.cert'].create(cert_vals)
            logging.getLogger(__name__).info(f"Created WHT certificate for payment {self.name} with partner {partner.name}")
            return cert
        except Exception as e:
            logging.getLogger(__name__).error(f"Failed to create WHT certificate: {e}")
            raise
