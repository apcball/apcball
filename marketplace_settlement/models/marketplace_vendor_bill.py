from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import re


class MarketplaceVendorBill(models.Model):
    _name = 'marketplace.vendor.bill'
    _description = 'Marketplace Vendor Bill'
    _order = 'date desc, name desc'
    _rec_name = 'document_reference'

    name = fields.Char('Name', required=True, copy=False, default='New')
    document_reference = fields.Char('Document Reference', required=True, 
                                   help='TR number for Shopee Tax Invoice or RC number for SPX Receipt')
    document_type = fields.Selection([
        ('shopee_tr', 'Shopee Tax Invoice (TR)'),
        ('spx_rc', 'SPX Receipt (RC)')
    ], string='Document Type', required=True)
    partner_id = fields.Many2one('res.partner', string='Vendor', required=True,
                               help='Shopee or SPX vendor partner')
    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Bill Journal', required=True,
                               domain="[('type', '=', 'purchase')]")
    vendor_bill_id = fields.Many2one('account.move', string='Created Vendor Bill', readonly=True)
    
    # Trade Channel Profile
    profile_id = fields.Many2one('marketplace.settlement.profile', string='Trade Channel Profile',
                               help='Profile containing default settings for this trade channel')
    trade_channel = fields.Selection(related='profile_id.trade_channel', string='Trade Channel', readonly=True)
    
    # Document lines
    line_ids = fields.One2many('marketplace.vendor.bill.line', 'bill_id', string='Lines')
    
    # Totals
    subtotal = fields.Monetary('Subtotal', currency_field='currency_id', compute='_compute_amounts', store=True)
    vat_amount = fields.Monetary('VAT Amount', currency_field='currency_id', compute='_compute_amounts', store=True)
    wht_amount = fields.Monetary('WHT Amount', currency_field='currency_id', compute='_compute_amounts', store=True)
    total_amount = fields.Monetary('Total Amount', currency_field='currency_id', compute='_compute_amounts', store=True)
    
    currency_id = fields.Many2one('res.currency', string='Currency', 
                                default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Company', 
                               default=lambda self: self.env.company)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('processed', 'Processed'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft')
    
    notes = fields.Text('Notes')

    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('marketplace.vendor.bill') or 'New'
        return super().create(vals)

    @api.depends('line_ids.amount', 'line_ids.vat_amount', 'line_ids.wht_amount')
    def _compute_amounts(self):
        for record in self:
            record.subtotal = sum(line.amount for line in record.line_ids)
            record.vat_amount = sum(line.vat_amount for line in record.line_ids)
            record.wht_amount = sum(line.wht_amount for line in record.line_ids)
            record.total_amount = record.subtotal + record.vat_amount - record.wht_amount

    @api.constrains('document_reference', 'document_type')
    def _check_unique_document_reference(self):
        for record in self:
            if record.document_reference:
                existing = self.search([
                    ('document_reference', '=', record.document_reference),
                    ('document_type', '=', record.document_type),
                    ('id', '!=', record.id)
                ])
                if existing:
                    raise ValidationError(
                        _('Document reference %s already exists for document type %s') % 
                        (record.document_reference, dict(record._fields['document_type'].selection)[record.document_type])
                    )

    @api.constrains('document_reference', 'document_type')
    def _check_document_reference_format(self):
        for record in self:
            if record.document_reference and record.document_type:
                if record.document_type == 'shopee_tr':
                    if not re.match(r'^TR[A-Z0-9]+$', record.document_reference):
                        raise ValidationError(_('Shopee Tax Invoice reference must start with "TR" followed by alphanumeric characters'))
                elif record.document_type == 'spx_rc':
                    if not re.match(r'^RC[A-Z0-9]+$', record.document_reference):
                        raise ValidationError(_('SPX Receipt reference must start with "RC" followed by alphanumeric characters'))

    @api.onchange('document_type')
    def _onchange_document_type(self):
        if self.document_type == 'shopee_tr':
            # Find Shopee profile
            profile = self.env['marketplace.settlement.profile'].get_profile_by_channel('shopee')
            if profile:
                self.profile_id = profile.id
                self._apply_profile_defaults()
        elif self.document_type == 'spx_rc':
            # Find SPX profile
            profile = self.env['marketplace.settlement.profile'].get_profile_by_channel('spx')
            if profile:
                self.profile_id = profile.id
                self._apply_profile_defaults()

    @api.onchange('profile_id')
    def _onchange_profile_id(self):
        """Apply profile defaults when profile is changed"""
        if self.profile_id:
            self._apply_profile_defaults()

    def _apply_profile_defaults(self):
        """Apply default values from the selected profile"""
        if not self.profile_id:
            return
            
        profile = self.profile_id
        
        # Set vendor partner if not already set
        if profile.vendor_partner_id and not self.partner_id:
            self.partner_id = profile.vendor_partner_id
            
        # Set purchase journal if not already set
        if profile.purchase_journal_id and not self.journal_id:
            self.journal_id = profile.purchase_journal_id
            
        # Clear existing lines and add default lines
        if not self.line_ids:
            self._add_default_lines_from_profile()

    def _add_default_lines_from_profile(self):
        """Add default lines based on profile configuration"""
        if not self.profile_id:
            return
            
        profile = self.profile_id
        lines_data = []
        
        if self.document_type == 'shopee_tr':
            # Default Shopee lines
            if profile.commission_account_id:
                lines_data.append({
                    'description': 'Platform Commission',
                    'account_id': profile.commission_account_id.id,
                    'amount': 0.0,
                    'vat_rate': profile.default_vat_rate,
                    'wht_rate': profile.default_wht_rate,
                    'sequence': 10
                })
            
            if profile.service_fee_account_id:
                lines_data.append({
                    'description': 'Service Fees',
                    'account_id': profile.service_fee_account_id.id,
                    'amount': 0.0,
                    'vat_rate': profile.default_vat_rate,
                    'wht_rate': profile.default_wht_rate,
                    'sequence': 20
                })
                
            if profile.advertising_account_id:
                lines_data.append({
                    'description': 'Advertising Fees',
                    'account_id': profile.advertising_account_id.id,
                    'amount': 0.0,
                    'vat_rate': profile.default_vat_rate,
                    'wht_rate': profile.default_wht_rate,
                    'sequence': 30
                })
                
        elif self.document_type == 'spx_rc':
            # Default SPX lines
            if profile.logistics_account_id:
                lines_data.append({
                    'description': 'Logistics Fees',
                    'account_id': profile.logistics_account_id.id,
                    'amount': 0.0,
                    'vat_rate': profile.default_vat_rate,
                    'wht_rate': profile.default_wht_rate,
                    'sequence': 10
                })
                
                lines_data.append({
                    'description': 'Shipping Charges',
                    'account_id': profile.logistics_account_id.id,
                    'amount': 0.0,
                    'vat_rate': profile.default_vat_rate,
                    'wht_rate': profile.default_wht_rate,
                    'sequence': 20
                })
        
        # Create lines
        for line_data in lines_data:
            line_data['bill_id'] = self.id
            self.env['marketplace.vendor.bill.line'].create(line_data)

    @api.onchange('document_reference')
    def _onchange_document_reference(self):
        """Auto-detect profile based on document reference pattern"""
        if self.document_reference and not self.profile_id:
            profile = self.env['marketplace.settlement.profile'].get_profile_by_document_pattern(
                self.document_reference
            )
            if profile:
                self.profile_id = profile.id

    def action_create_vendor_bill(self):
        """Create vendor bill from marketplace document"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft documents can be processed'))
        
        if not self.line_ids:
            raise UserError(_('Please add at least one line before creating vendor bill'))
        
        # Create vendor bill
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.date,
            'journal_id': self.journal_id.id,
            'ref': self.document_reference,
            'narration': f'Marketplace document: {self.document_reference}\n{self.notes or ""}',
            'invoice_line_ids': []
        }
        
        # Add invoice lines
        for line in self.line_ids:
            line_vals = {
                'name': line.description,
                'account_id': line.account_id.id,
                'quantity': 1,
                'price_unit': line.amount,
                'tax_ids': []
            }
            
            # Add VAT tax if applicable
            if line.vat_amount > 0:
                vat_tax = self._get_vat_tax()
                if vat_tax:
                    line_vals['tax_ids'].append((4, vat_tax.id))
            
            # Add WHT tax if applicable
            if line.wht_amount > 0:
                wht_tax = self._get_wht_tax(line.wht_rate)
                if wht_tax:
                    line_vals['tax_ids'].append((4, wht_tax.id))
            
            bill_vals['invoice_line_ids'].append((0, 0, line_vals))
        
        # Create the bill
        vendor_bill = self.env['account.move'].create(bill_vals)
        
        # Update state and link
        self.write({
            'vendor_bill_id': vendor_bill.id,
            'state': 'processed'
        })
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': vendor_bill.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _get_vat_tax(self):
        """Get VAT purchase tax (7%)"""
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', 7),
            ('amount_type', '=', 'percent')
        ], limit=1)

    def _get_wht_tax(self, rate):
        """Get WHT tax by rate"""
        return self.env['account.tax'].search([
            ('type_tax_use', '=', 'purchase'),
            ('amount', '=', -abs(rate)),  # WHT taxes are negative
            ('amount_type', '=', 'percent')
        ], limit=1)

    def action_view_vendor_bill(self):
        """View created vendor bill"""
        self.ensure_one()
        if not self.vendor_bill_id:
            raise UserError(_('No vendor bill has been created yet'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Vendor Bill'),
            'res_model': 'account.move',
            'res_id': self.vendor_bill_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_cancel(self):
        """Cancel the document"""
        self.ensure_one()
        if self.vendor_bill_id and self.vendor_bill_id.state == 'posted':
            raise UserError(_('Cannot cancel document with posted vendor bill'))
        self.state = 'cancelled'

    def action_reset_to_draft(self):
        """Reset to draft"""
        self.ensure_one()
        if self.vendor_bill_id:
            raise UserError(_('Cannot reset to draft when vendor bill exists'))
        self.state = 'draft'


class MarketplaceVendorBillLine(models.Model):
    _name = 'marketplace.vendor.bill.line'
    _description = 'Marketplace Vendor Bill Line'
    _order = 'sequence, id'

    bill_id = fields.Many2one('marketplace.vendor.bill', string='Vendor Bill', required=True, ondelete='cascade')
    sequence = fields.Integer('Sequence', default=10)
    
    description = fields.Char('Description', required=True)
    account_id = fields.Many2one('account.account', string='Account', required=True,
                               domain="[('account_type', 'in', ['expense', 'asset_expense'])]")
    amount = fields.Monetary('Amount', currency_field='currency_id', required=True)
    
    # Tax related fields
    vat_rate = fields.Float('VAT Rate (%)', default=0.0)
    vat_amount = fields.Monetary('VAT Amount', currency_field='currency_id', compute='_compute_vat_amount', store=True)
    wht_rate = fields.Float('WHT Rate (%)', default=0.0)
    wht_amount = fields.Monetary('WHT Amount', currency_field='currency_id', compute='_compute_wht_amount', store=True)
    
    currency_id = fields.Many2one(related='bill_id.currency_id', string='Currency', readonly=True)
    
    @api.depends('amount', 'vat_rate')
    def _compute_vat_amount(self):
        for line in self:
            line.vat_amount = line.amount * (line.vat_rate / 100.0)
    
    @api.depends('amount', 'wht_rate')
    def _compute_wht_amount(self):
        for line in self:
            line.wht_amount = line.amount * (line.wht_rate / 100.0)

    @api.onchange('bill_id.document_type', 'bill_id.profile_id')
    def _onchange_document_type(self):
        """Set default rates based on document type and profile"""
        if self.bill_id and self.bill_id.profile_id:
            profile = self.bill_id.profile_id
            self.vat_rate = profile.default_vat_rate
            self.wht_rate = profile.default_wht_rate
