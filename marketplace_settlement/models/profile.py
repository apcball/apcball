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
    
    # Vendor Bill Configuration
    vendor_partner_id = fields.Many2one('res.partner', string='Default Vendor Partner',
                                       help='Default vendor partner for creating vendor bills from this channel')
    purchase_journal_id = fields.Many2one('account.journal', string='Purchase Journal',
                                         domain="[('type', '=', 'purchase')]",
                                         help='Default journal for vendor bills')
    
    # Tax Configuration
    default_vat_rate = fields.Float('Default VAT Rate (%)', default=0.0,
                                   help='Default VAT rate for this channel (e.g., 7.0 for 7%)')
    default_wht_rate = fields.Float('Default WHT Rate (%)', default=0.0,
                                   help='Default withholding tax rate for this channel (e.g., 3.0 for 3%)')
    vat_tax_id = fields.Many2one('account.tax', string='VAT Purchase Tax',
                                domain="[('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'percent')]",
                                help='Purchase VAT tax to use for vendor bills')
    wht_tax_id = fields.Many2one('account.tax', string='WHT Tax',
                                domain="[('type_tax_use', '=', 'purchase'), ('amount_type', '=', 'percent')]",
                                help='Withholding tax to use for vendor bills')
    
    # Default Expense Accounts
    commission_account_id = fields.Many2one('account.account', string='Commission Account',
                                          domain="[('account_type', 'in', ['expense', 'asset_expense'])]",
                                          help='Default account for marketplace commission fees')
    service_fee_account_id = fields.Many2one('account.account', string='Service Fee Account',
                                           domain="[('account_type', 'in', ['expense', 'asset_expense'])]",
                                           help='Default account for service fees')
    advertising_account_id = fields.Many2one('account.account', string='Advertising Account',
                                           domain="[('account_type', 'in', ['expense', 'asset_expense'])]",
                                           help='Default account for advertising fees')
    
    # Thai Localization fields
    use_thai_wht = fields.Boolean('Use Thai WHT', default=False,
                                 help='Enable Thai withholding tax processing for this profile')
    thai_income_tax_form = fields.Selection([
        ('pnd1', 'PND1'),
        ('pnd2', 'PND2'),
        ('pnd3', 'PND3'),
        ('pnd3a', 'PND3a'),
        ('pnd53', 'PND53'),
    ], string='Default Income Tax Form', help='Default Thai income tax form for this channel')
    thai_wht_income_type = fields.Selection([
        ('1', '1. เงินเดือน ค่าจ้าง ฯลฯ 40(1)'),
        ('2', '2. ค่าธรรมเนียม ค่านายหน้า ฯลฯ 40(2)'),
        ('3', '3. ค่าแห่งลิขสิทธิ์ ฯลฯ 40(3)'),
        ('4A', '4. ดอกเบี้ย ฯลฯ 40(4)ก'),
    ], string='Default WHT Income Type', help='Default Thai WHT income type for this channel')
    
    logistics_account_id = fields.Many2one('account.account', string='Logistics Account',
                                         domain="[('account_type', 'in', ['expense', 'asset_expense'])]",
                                         help='Default account for logistics/shipping fees')
    other_expense_account_id = fields.Many2one('account.account', string='Other Expenses Account',
                                             domain="[('account_type', 'in', ['expense', 'asset_expense'])]",
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
            'vat_rate': self.default_vat_rate,
            'wht_rate': self.default_wht_rate,
        }

    @api.onchange('trade_channel')
    def _onchange_trade_channel(self):
        """Set default values based on trade channel"""
        if self.trade_channel:
            # Set default name
            channel_names = dict(self._fields['trade_channel'].selection)
            self.name = f"{channel_names.get(self.trade_channel)} Profile"
            
            # Set default patterns and rates based on channel
            if self.trade_channel == 'shopee':
                self.invoice_pattern = 'TR'
                self.default_vat_rate = 7.0
                self.default_wht_rate = 3.0
            elif self.trade_channel == 'lazada':
                self.default_vat_rate = 7.0
                self.default_wht_rate = 3.0

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
                'default_fee_account_id': self.commission_account_id.id if self.commission_account_id else False,
            },
        }

    @api.onchange('trade_channel')
    def _onchange_trade_channel(self):
        """Set default values based on trade channel"""
        if self.trade_channel:
            # Set default name
            channel_names = dict(self._fields['trade_channel'].selection)
            self.name = f"{channel_names.get(self.trade_channel)} Profile"
            
            # Set default patterns and rates based on channel
            if self.trade_channel == 'shopee':
                self.invoice_pattern = 'TR'
                self.default_vat_rate = 7.0
                self.default_wht_rate = 3.0
            elif self.trade_channel == 'spx':
                self.receipt_pattern = 'RC'
                self.default_vat_rate = 0.0
                self.default_wht_rate = 1.0
            elif self.trade_channel == 'lazada':
                self.invoice_pattern = 'LZ'
                self.default_vat_rate = 7.0
                self.default_wht_rate = 3.0
            elif self.trade_channel == 'tiktok':
                self.invoice_pattern = 'TT'
                self.default_vat_rate = 7.0
                self.default_wht_rate = 3.0
