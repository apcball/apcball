from odoo import models, fields, api, _


class MarketplaceSettlementProfile(models.Model):
    _name = 'marketplace.settlement.profile'
    _description = 'Marketplace Settlement Profile per Channel'
    _rec_name = 'name'

    name = fields.Char('Profile Name', required=True)
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'),
        ('lazada', 'Lazada'),
        ('nocnoc', 'Noc Noc'),
        ('tiktok', 'Tiktok'),
        ('spx', 'SPX'),
        ('other', 'Other'),
    ], string='Trade Channel', required=True)
    
    # Settlement Configuration
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner')
    journal_id = fields.Many2one('account.journal', string='Default Journal')
    settlement_account_id = fields.Many2one('account.account', string='Default Settlement Account')
    
    # Default Expense Accounts - Allow all account types
    commission_account_id = fields.Many2one('account.account', string='Commission Account',
                                          help='Default account for marketplace commission fees')
    service_fee_account_id = fields.Many2one('account.account', string='Service Fee Account',
                                           help='Default account for service fees')
    advertising_account_id = fields.Many2one('account.account', string='Advertising Account',
                                           help='Default account for advertising fees')
    logistics_account_id = fields.Many2one('account.account', string='Logistics Account',
                                         help='Default account for logistics/shipping fees')
    other_expense_account_id = fields.Many2one('account.account', string='Other Expenses Account',
                                             help='Default account for other miscellaneous expenses')
    
    # Document Patterns
    invoice_pattern = fields.Char('Tax Invoice Pattern', 
                                 help='Pattern for tax invoice references (e.g., TR for Shopee)')
    receipt_pattern = fields.Char('Receipt Pattern',
                                 help='Pattern for receipt references (e.g., RC for SPX)')
    
    # Channel-specific settings
    active = fields.Boolean('Active', default=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    notes = fields.Text('Notes', help='Additional notes for this trade channel profile')

    @api.model
    def get_profile_by_channel(self, trade_channel):
        """Get active profile for a trade channel"""
        return self.search([
            ('trade_channel', '=', trade_channel),
            ('active', '=', True)
        ], limit=1)

    @api.model
    def get_profile_by_document_pattern(self, document_reference):
        """Get profile based on document reference pattern"""
        profiles = self.search([('active', '=', True)])
        for profile in profiles:
            if profile.invoice_pattern and document_reference.startswith(profile.invoice_pattern):
                return profile
            if profile.receipt_pattern and document_reference.startswith(profile.receipt_pattern):
                return profile
        return self.env['marketplace.settlement.profile']

    def get_default_account_for_type(self, account_type):
        """Get default account for a specific expense type"""
        self.ensure_one()
        account_mapping = {
            'commission': self.commission_account_id,
            'service': self.service_fee_account_id,
            'advertising': self.advertising_account_id,
            'logistics': self.logistics_account_id,
            'shipping': self.logistics_account_id,
            'other': self.other_expense_account_id,
        }
        return account_mapping.get(account_type, self.other_expense_account_id)

    def get_default_line_config(self, expense_type):
        """Get default line configuration for vendor bills"""
        self.ensure_one()
        account = self.get_default_account_for_type(expense_type)
        return {
            'account_id': account.id if account else False,
        }

    @api.onchange('trade_channel')
    def _onchange_trade_channel(self):
        """Set default values based on trade channel"""
        if self.trade_channel:
            # Set default name
            channel_names = dict(self._fields['trade_channel'].selection)
            self.name = f"{channel_names.get(self.trade_channel)} Profile"
            
            # Set default patterns based on channel
            if self.trade_channel == 'shopee':
                self.invoice_pattern = 'TR'
            elif self.trade_channel == 'spx':
                self.receipt_pattern = 'RC'
            elif self.trade_channel == 'lazada':
                self.invoice_pattern = 'LZ'
            elif self.trade_channel == 'tiktok':
                self.invoice_pattern = 'TT'

    def action_create_settlement_with_profile(self):
        """Action to create settlement using this profile"""
        self.ensure_one()
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Settlement with %s Profile') % self.name,
            'res_model': 'marketplace.settlement.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_profile_id': self.id,
                'default_trade_channel': self.trade_channel,
                'default_marketplace_partner_id': self.marketplace_partner_id.id if self.marketplace_partner_id else False,
                'default_journal_id': self.journal_id.id if self.journal_id else False,
                'default_settlement_account_id': self.settlement_account_id.id if self.settlement_account_id else False,
                # Include profile for settlement creation
                'profile_setup': {
                    'commission_account_id': self.commission_account_id.id if self.commission_account_id else False,
                    'service_fee_account_id': self.service_fee_account_id.id if self.service_fee_account_id else False,
                    'advertising_account_id': self.advertising_account_id.id if self.advertising_account_id else False,
                    'logistics_account_id': self.logistics_account_id.id if self.logistics_account_id else False,
                    'other_expense_account_id': self.other_expense_account_id.id if self.other_expense_account_id else False,
                },
            },
        }

    def action_create_vendor_bill_with_profile(self):
        """Action to create vendor bill using profile account settings"""
        self.ensure_one()
        
        # Create vendor bill with profile account defaults
        vendor_bill_values = {
            'move_type': 'in_invoice',
            'partner_id': self.marketplace_partner_id.id if self.marketplace_partner_id else False,
            'invoice_date': fields.Date.context_today(self),
            'ref': f'{self.trade_channel.upper()}-FEES-{fields.Date.context_today(self)}',
        }
        
        # Prepare invoice lines with profile accounts
        invoice_lines = []
        if self.commission_account_id:
            invoice_lines.append((0, 0, {
                'name': 'Commission Fee',
                'account_id': self.commission_account_id.id,
                'quantity': 1,
                'price_unit': 0.0,  # User will fill in the amount
            }))
        
        if self.service_fee_account_id:
            invoice_lines.append((0, 0, {
                'name': 'Service Fee', 
                'account_id': self.service_fee_account_id.id,
                'quantity': 1,
                'price_unit': 0.0,
            }))
            
        if self.advertising_account_id:
            invoice_lines.append((0, 0, {
                'name': 'Advertising Fee',
                'account_id': self.advertising_account_id.id,
                'quantity': 1,
                'price_unit': 0.0,
            }))
            
        if self.logistics_account_id:
            invoice_lines.append((0, 0, {
                'name': 'Logistics Fee',
                'account_id': self.logistics_account_id.id,
                'quantity': 1,
                'price_unit': 0.0,
            }))
        
        if invoice_lines:
            vendor_bill_values['invoice_line_ids'] = invoice_lines
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Vendor Bill with %s Profile') % self.name,
            'res_model': 'account.move',
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'default_move_type': 'in_invoice',
                **vendor_bill_values,
            },
        }
