from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MarketplaceSettlementWizard(models.TransientModel):
    _name = 'marketplace.settlement.wizard'
    _description = 'Wizard to create marketplace settlement'

    name = fields.Char('Settlement Ref', required=True)
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner', required=True)
    profile_id = fields.Many2one('marketplace.settlement.profile', string='Profile')
    journal_id = fields.Many2one('account.journal', string='Journal', required=True)
    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'),
        ('lazada', 'Lazada'),
        ('nocnoc', 'Noc Noc'),
        ('tiktok', 'Tiktok'),
        ('spx', 'SPX'),
        ('other', 'Other')
    ], string='Trade Channel', required=True)
    invoice_ids = fields.Many2many('account.move', string='Invoices')
    auto_filter = fields.Boolean('Auto Filter Invoices', default=True, help="Automatically filter invoices based on selected trade channel")
    date_from = fields.Date('Date From', help="Filter invoices from this date")
    date_to = fields.Date('Date To', help="Filter invoices until this date")
    settlement_account_id = fields.Many2one('account.account', string='Settlement Account', help='Account to post the marketplace aggregate line to (optional)')
    invoice_count = fields.Integer('Invoice Count', compute='_compute_invoice_count')
    total_amount = fields.Monetary('Total Amount', compute='_compute_total_amount', currency_field='currency_id')
    total_deductions = fields.Monetary('Total Deductions', compute='_compute_total_amount', currency_field='currency_id')
    net_settlement_amount = fields.Monetary('Net Settlement Amount', compute='_compute_total_amount', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)
    
    # Note: Deduction fields removed - fees should be handled through vendor bills for proper tax documentation
    
    # Settlement posting options
    auto_post_settlement = fields.Boolean('Auto Post Settlement', default=False,
                                         help='Automatically post the settlement after creation')

    @api.model
    def default_get(self, fields_list):
        """Set default values and auto-populate from profile if available"""
        res = super().default_get(fields_list)
        
        # Try to find a profile from context or default profile
        profile_id = self.env.context.get('default_profile_id')
        if not profile_id:
            # Try to get default profile for most common trade channel (Shopee)
            default_profile = self.env['marketplace.settlement.profile'].search([
                ('trade_channel', '=', 'shopee'),
                ('active', '=', True)
            ], limit=1)
            if default_profile:
                profile_id = default_profile.id
                
        if profile_id:
            res['profile_id'] = profile_id
            profile = self.env['marketplace.settlement.profile'].browse(profile_id)
            
            # Apply profile defaults
            if profile.trade_channel:
                res['trade_channel'] = profile.trade_channel
            if profile.marketplace_partner_id:
                res['marketplace_partner_id'] = profile.marketplace_partner_id.id
            if profile.journal_id:
                res['journal_id'] = profile.journal_id.id
            if profile.settlement_account_id:
                res['settlement_account_id'] = profile.settlement_account_id.id
            
            # Apply vendor bill defaults from profile
            if profile.vendor_partner_id:
                res['vendor_partner_id'] = profile.vendor_partner_id.id
            if profile.purchase_journal_id:
                res['purchase_journal_id'] = profile.purchase_journal_id.id
            if profile.vat_tax_id:
                res['vat_tax_id'] = profile.vat_tax_id.id
            if profile.wht_tax_id:
                res['wht_tax_id'] = profile.wht_tax_id.id
                
        return res

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    @api.depends('invoice_ids')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.invoice_ids.mapped('amount_residual'))
            record.total_deductions = 0.0  # Deductions now handled through vendor bills
            record.net_settlement_amount = record.total_amount

    @api.onchange('trade_channel', 'date_from', 'date_to')
    def _onchange_trade_channel(self):
        """Automatically filter and populate invoices when trade channel is selected"""
        # Auto-suggest profile for selected trade channel if no profile selected
        if self.trade_channel and not self.profile_id:
            Profile = self.env['marketplace.settlement.profile']
            matching_profile = Profile.search([
                ('trade_channel', '=', self.trade_channel),
                ('active', '=', True)
            ], limit=1)
            
            if matching_profile:
                # Don't auto-assign, but make it available for suggestion
                # This prevents overwriting user's explicit profile choice
                pass
                
        # Load profile defaults for this channel if no explicit profile selected  
        if self.trade_channel and not self.profile_id:
            Profile = self.env['marketplace.settlement.profile'].sudo()
            prof = Profile.search([('trade_channel', '=', self.trade_channel)], limit=1)
            if prof:
                # only set defaults when fields are empty to avoid overwriting manual choices
                if not self.marketplace_partner_id:
                    self.marketplace_partner_id = prof.marketplace_partner_id
                if not self.journal_id:
                    self.journal_id = prof.journal_id
                if not self.settlement_account_id:
                    self.settlement_account_id = prof.settlement_account_id
                # Also set expense accounts - removed as fees handled through vendor bills
                # if not self.fee_account_id and prof.commission_account_id:
                #     self.fee_account_id = prof.commission_account_id

        if self.trade_channel and self.auto_filter:
            # Build domain for filtering invoices
            domain = [
                ('state', '=', 'posted'),
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('trade_channel', '=', self.trade_channel),
                ('amount_residual', '!=', 0.0)
            ]

            # Add date filters if specified
            if self.date_from:
                domain.append(('invoice_date', '>=', self.date_from))
            if self.date_to:
                domain.append(('invoice_date', '<=', self.date_to))

            # Find matching invoices
            matching_invoices = self.env['account.move'].search(domain)
            self.invoice_ids = [(6, 0, matching_invoices.ids)]

            # Update settlement reference name if not manually set
            if not self.name or self.name.startswith('SETTLE-'):
                # fields.Date.context_today may return a date or a string depending on context;
                # normalize to string before using replace.
                date_suffix = str(fields.Date.context_today(self)).replace('-', '')
                if self.date_from and self.date_to:
                    date_suffix = f"{str(self.date_from).replace('-', '')}-{str(self.date_to).replace('-', '')}"
                self.name = f'SETTLE-{self.trade_channel.upper()}-{date_suffix}'

        # Return domain for manual selection in the view
        if self.trade_channel:
            domain = [
                ('state', '=', 'posted'),
                ('move_type', 'in', ['out_invoice', 'out_refund']),
                ('trade_channel', '=', self.trade_channel),
                ('amount_residual', '!=', 0.0)
            ]
            if self.date_from:
                domain.append(('invoice_date', '>=', self.date_from))
            if self.date_to:
                domain.append(('invoice_date', '<=', self.date_to))
            return {'domain': {'invoice_ids': domain}}

    @api.onchange('journal_id')
    def _onchange_journal_id_set_settlement_account(self):
        """When user selects a journal, default the settlement account from the journal's default account."""
        if self.journal_id:
            acct = getattr(self.journal_id, 'default_account_id', False) or getattr(self.journal_id, 'default_debit_account_id', False) or False
            self.settlement_account_id = acct.id if acct else False

    @api.onchange('auto_filter', 'trade_channel')
    def _onchange_auto_filter(self):
        """Toggle auto-filtering behavior"""
        if self.auto_filter and self.trade_channel:
            self._onchange_trade_channel()
        elif not self.auto_filter:
            self.invoice_ids = [(5, 0, 0)]  # Clear invoices

    @api.onchange('profile_id')
    def _onchange_profile(self):
        """When a profile is selected, populate related defaults and refresh invoices."""
        if not self.profile_id:
            return
        prof = self.profile_id
        
        # Always set trade channel from profile
        if prof.trade_channel:
            self.trade_channel = prof.trade_channel
            
        # Apply marketplace partner (always override if profile has one)
        if prof.marketplace_partner_id:
            self.marketplace_partner_id = prof.marketplace_partner_id
            
        # Apply journal (always override if profile has one)
        if prof.journal_id:
            self.journal_id = prof.journal_id
            
        # Apply settlement account
        if prof.settlement_account_id:
            self.settlement_account_id = prof.settlement_account_id
            
        # Apply default expense accounts - removed as fees handled through vendor bills
        # if prof.commission_account_id and not self.fee_account_id:
        #     self.fee_account_id = prof.commission_account_id
        
        # Apply vendor bill configuration from profile
        if prof.vendor_partner_id and not self.vendor_partner_id:
            self.vendor_partner_id = prof.vendor_partner_id
        if prof.purchase_journal_id and not self.purchase_journal_id:
            self.purchase_journal_id = prof.purchase_journal_id
        if prof.vat_tax_id and not self.vat_tax_id:
            self.vat_tax_id = prof.vat_tax_id
        if prof.wht_tax_id and not self.wht_tax_id:
            self.wht_tax_id = prof.wht_tax_id
            
        # Apply VAT account from profile VAT tax configuration
        if prof.vat_tax_id and not self.vat_account_id:
            # Try to get account from tax configuration
            vat_tax = prof.vat_tax_id
            if vat_tax.invoice_repartition_line_ids:
                for line in vat_tax.invoice_repartition_line_ids:
                    if line.account_id and 'input' in line.account_id.name.lower():
                        self.vat_account_id = line.account_id
                        break
                        
        # Fee-related calculations are now handled through vendor bills
        # No automatic calculations needed in settlement wizard
        
        # Enable auto-filter and refresh invoices
        self.auto_filter = True
        self._onchange_trade_channel()

        # Remove all fee-related field validations - these are now handled through vendor bills
        # Removed: fee validation, VAT validation, WHT validation}

    def action_create(self):
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(_('Please select invoices to settle.'))

        # Remove deduction validation - fees now handled through vendor bills
        # No longer need to validate fee accounts since they are in vendor bills

        # Create settlement (always as draft first) - deduction fields removed
        settlement = self.env['marketplace.settlement'].create({
            'name': self.name,
            'marketplace_partner_id': self.marketplace_partner_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'trade_channel': self.trade_channel,
            'invoice_ids': [(6, 0, self.invoice_ids.ids)],
            'settlement_account_id': self.settlement_account_id.id if self.settlement_account_id else False,
            # Store profile reference for future use
            'profile_id': self.profile_id.id if self.profile_id else False,
        })

        # Post settlement if auto-post is enabled
        if self.auto_post_settlement:
            try:
                action = settlement.action_create_settlement()
            except Exception as e:
                raise UserError(_('Failed to post settlement: %s') % str(e))
        
        # Prepare success message with new workflow guidance
        messages = [_('Settlement "%s" created successfully as draft.') % settlement.name]
        if self.auto_post_settlement:
            messages.append(_('Settlement has been posted.'))
        else:
            messages.append(_('Settlement is in draft state. You can review and post it manually.'))

        # Guidance for new workflow
        messages.append(_('\nNew Workflow:'))
        messages.append(_('1. Create Vendor Bills for marketplace fees (Shopee/SPX) separately'))
        messages.append(_('2. Link vendor bills to this settlement'))
        messages.append(_('3. Use Net-off AR/AP button to offset receivables against payables'))
        messages.append(_('4. Reconcile remaining net amount with bank statement'))

        warning_msg = '\n'.join(messages)

        # Return action to open settlement form
        return {
            'type': 'ir.actions.act_window',
            'name': _('Marketplace Settlement'),
            'res_model': 'marketplace.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {'create': False},
            'flags': {
                'mode': 'readonly' if self.auto_post_settlement else 'edit',
            },
            'warning': {
                'title': _('Settlement Created'),
                'message': warning_msg,
            },
        }

    def action_refresh_invoices(self):
        """Manual action to refresh invoice list based on current trade channel"""
        self._onchange_trade_channel()
        return None
