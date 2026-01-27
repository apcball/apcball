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
    
    # Trade Channel Profile (Optional - Users can configure manually)
    profile_id = fields.Many2one('marketplace.settlement.profile', string='Trade Channel Profile',
                               help='Optional profile for default settings. Users can configure manually instead.')
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'),
        ('lazada', 'Lazada'),
        ('nocnoc', 'Noc Noc'),
        ('tiktok', 'Tiktok'),
        ('spx', 'SPX'),
        ('other', 'Other'),
    ], string='Trade Channel', help='Trade channel for this vendor bill')
    
    # Manual Configuration Fields (when not using profile)
    use_manual_config = fields.Boolean('Manual Configuration', default=False,
                                     help='Enable manual configuration instead of using profile defaults')
    manual_vat_rate = fields.Float('VAT Rate (%)', default=0.0,
                                 help='VAT rate for manual configuration')
    manual_wht_rate = fields.Float('WHT Rate (%)', default=0.0,
                                 help='Withholding tax rate for manual configuration')
    
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
        """Auto-detect trade channel and suggest profile, but allow manual override"""
        if self.document_type == 'shopee_tr':
            self.trade_channel = 'shopee'
            # Suggest profile but don't force it
            profile = self.env['marketplace.settlement.profile'].get_profile_by_channel('shopee')
            if profile and not self.use_manual_config:
                self.profile_id = profile.id
                self._apply_profile_defaults()
        elif self.document_type == 'spx_rc':
            self.trade_channel = 'spx'
            # Suggest profile but don't force it
            profile = self.env['marketplace.settlement.profile'].get_profile_by_channel('spx')
            if profile and not self.use_manual_config:
                self.profile_id = profile.id
                self._apply_profile_defaults()

    @api.onchange('use_manual_config')
    def _onchange_use_manual_config(self):
        """Switch between profile and manual configuration"""
        if self.use_manual_config:
            # Clear profile when switching to manual
            self.profile_id = False
        else:
            # Try to apply profile when switching back
            if self.trade_channel:
                profile = self.env['marketplace.settlement.profile'].get_profile_by_channel(self.trade_channel)
                if profile:
                    self.profile_id = profile.id
                    self._apply_profile_defaults()

    @api.onchange('trade_channel')
    def _onchange_trade_channel(self):
        """Update profile suggestion when trade channel changes"""
        if self.trade_channel and not self.use_manual_config:
            profile = self.env['marketplace.settlement.profile'].get_profile_by_channel(self.trade_channel)
            if profile:
                self.profile_id = profile.id
                self._apply_profile_defaults()

    @api.onchange('profile_id')
    def _onchange_profile_id(self):
        """Apply profile defaults when profile is changed"""
        if self.profile_id and not self.use_manual_config:
            self._apply_profile_defaults()

    def _apply_profile_defaults(self):
        """Apply default values from the selected profile"""
        if not self.profile_id or self.use_manual_config:
            return
            
        profile = self.profile_id
        
        # Set vendor partner if not already set
        if profile.vendor_partner_id and not self.partner_id:
            self.partner_id = profile.vendor_partner_id
            
        # Set purchase journal if not already set
        if profile.purchase_journal_id and not self.journal_id:
            self.journal_id = profile.purchase_journal_id
            
        # Update manual rates from profile
        self.manual_vat_rate = profile.default_vat_rate
        self.manual_wht_rate = profile.default_wht_rate
            
        # Clear existing lines and add default lines only if no lines exist
        if not self.line_ids:
            self._add_default_lines_from_profile()

    def _add_default_lines_from_profile(self):
        """Add default lines based on profile configuration or manual setup"""
        if self.use_manual_config:
            # For manual configuration, add basic lines that user can customize
            self._add_manual_default_lines()
        elif self.profile_id:
            self._add_profile_default_lines()

    def _add_manual_default_lines(self):
        """Add basic default lines for manual configuration"""
        lines_data = []
        
        if self.document_type == 'shopee_tr':
            lines_data = [
                {
                    'description': 'Platform Commission',
                    'amount': 0.0,
                    'vat_rate': self.manual_vat_rate,
                    'wht_rate': self.manual_wht_rate,
                    'sequence': 10
                },
                {
                    'description': 'Service Fees',
                    'amount': 0.0,
                    'vat_rate': self.manual_vat_rate,
                    'wht_rate': self.manual_wht_rate,
                    'sequence': 20
                },
                {
                    'description': 'Advertising Fees',
                    'amount': 0.0,
                    'vat_rate': self.manual_vat_rate,
                    'wht_rate': self.manual_wht_rate,
                    'sequence': 30
                }
            ]
        elif self.document_type == 'spx_rc':
            lines_data = [
                {
                    'description': 'Logistics Fees',
                    'amount': 0.0,
                    'vat_rate': self.manual_vat_rate,
                    'wht_rate': self.manual_wht_rate,
                    'sequence': 10
                },
                {
                    'description': 'Shipping Charges',
                    'amount': 0.0,
                    'vat_rate': self.manual_vat_rate,
                    'wht_rate': self.manual_wht_rate,
                    'sequence': 20
                }
            ]
        
        # Create lines
        for line_data in lines_data:
            line_data['bill_id'] = self.id
            self.env['marketplace.vendor.bill.line'].create(line_data)

    def _add_profile_default_lines(self):
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

    def action_link_vendor_bill(self):
        """Open wizard to link an existing vendor bill to this marketplace document"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft documents can be linked'))
        
        # Return action to open the bill link wizard
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link Vendor Bill'),
            'res_model': 'bill.link.wizard',
            'view_mode': 'form',
            'context': {
                'default_marketplace_document_id': self.id,
            },
            'target': 'new',
        }
    
    def action_create_bill_from_template(self):
        """Create a new vendor bill with pre-filled data from this document"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft documents can be processed'))
        
        # Prepare bill values based on marketplace document
        bill_vals = {
            'move_type': 'in_invoice',
            'partner_id': self.partner_id.id,
            'invoice_date': self.date,
            'journal_id': self.journal_id.id if self.journal_id else False,
            'ref': self.document_reference,
            'trade_channel': self.trade_channel,
            'settlement_ref': f'MP-{self.document_reference}',
            'narration': f'Marketplace document: {self.document_reference}\n{self.notes or ""}',
        }
        
        # Return action to create new bill with pre-filled data
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Vendor Bill'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'context': dict(self.env.context, default_move_type='in_invoice', **bill_vals),
            'target': 'current',
        }

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

    def action_toggle_manual_config(self):
        """Toggle between manual configuration and profile configuration"""
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Can only change configuration for draft documents'))
        
        self.use_manual_config = not self.use_manual_config
        
        # If there are existing lines, ask user what to do
        if self.line_ids:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Configuration Changed'),
                'res_model': 'marketplace.config.change.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_vendor_bill_id': self.id,
                    'default_use_manual_config': self.use_manual_config,
                },
            }
        else:
            # No lines exist, just apply new configuration
            if self.use_manual_config:
                self._add_manual_default_lines()
            else:
                self._add_profile_default_lines()
        
        return True


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

    @api.onchange('bill_id.document_type', 'bill_id.profile_id', 'bill_id.use_manual_config')
    def _onchange_document_type(self):
        """Set default rates based on document type, profile, or manual configuration"""
        if not self.bill_id:
            return
            
        if self.bill_id.use_manual_config:
            # Use manual rates
            self.vat_rate = self.bill_id.manual_vat_rate
            self.wht_rate = self.bill_id.manual_wht_rate
        elif self.bill_id.profile_id:
            # Use profile rates
            profile = self.bill_id.profile_id
            self.vat_rate = profile.default_vat_rate
            self.wht_rate = profile.default_wht_rate
        else:
            # Default rates based on trade channel
            if self.bill_id.trade_channel == 'shopee':
                self.vat_rate = 7.0
                self.wht_rate = 3.0
            elif self.bill_id.trade_channel == 'spx':
                self.vat_rate = 0.0
                self.wht_rate = 1.0
            else:
                self.vat_rate = 0.0
                self.wht_rate = 0.0

    def get_account_suggestions(self):
        """Get account suggestions based on line description"""
        if not self.description:
            return []
            
        description_lower = self.description.lower()
        suggestions = []
        
        # Get expense accounts
        expense_accounts = self.env['account.account'].search([
            ('account_type', 'in', ['expense', 'asset_expense']),
            ('company_id', '=', self.bill_id.company_id.id)
        ])
        
        # Suggest accounts based on keywords in description
        keywords = {
            'commission': ['commission', 'fee', 'charge'],
            'advertising': ['advertising', 'ads', 'promotion', 'marketing'],
            'logistics': ['logistics', 'shipping', 'delivery', 'transport'],
            'service': ['service', 'platform', 'system']
        }
        
        for account in expense_accounts:
            account_name_lower = account.name.lower()
            for category, words in keywords.items():
                if any(word in description_lower for word in words):
                    if category in account_name_lower or any(word in account_name_lower for word in words):
                        suggestions.append(account)
                        break
        
        return suggestions[:5]  # Return top 5 suggestions
