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
        ('other', 'Other')
    ], string='Trade Channel', required=True)
    invoice_ids = fields.Many2many('account.move', string='Invoices')
    auto_filter = fields.Boolean('Auto Filter Invoices', default=True, help="Automatically filter invoices based on selected trade channel")
    date_from = fields.Date('Date From', help="Filter invoices from this date")
    date_to = fields.Date('Date To', help="Filter invoices until this date")
    settlement_account_id = fields.Many2one('account.account', string='Settlement Account', help='Account to post the marketplace aggregate line to (optional)')
    invoice_count = fields.Integer('Invoice Count', compute='_compute_invoice_count')
    total_amount = fields.Monetary('Total Amount', compute='_compute_total_amount', currency_field='currency_id')
    currency_id = fields.Many2one('res.currency', default=lambda self: self.env.company.currency_id)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    @api.depends('invoice_ids')
    def _compute_total_amount(self):
        for record in self:
            record.total_amount = sum(record.invoice_ids.mapped('amount_residual'))

    @api.onchange('trade_channel', 'date_from', 'date_to')
    def _onchange_trade_channel(self):
        """Automatically filter and populate invoices when trade channel is selected"""
        # load profile defaults for this channel if any (only if no explicit profile selected)
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
        # set trade channel from profile if not set or different
        if prof.trade_channel:
            self.trade_channel = prof.trade_channel
        # apply defaults (do not override manual values)
        if prof.marketplace_partner_id and not self.marketplace_partner_id:
            self.marketplace_partner_id = prof.marketplace_partner_id
        if prof.journal_id and not self.journal_id:
            self.journal_id = prof.journal_id
        if prof.settlement_account_id and not self.settlement_account_id:
            self.settlement_account_id = prof.settlement_account_id
        # ensure auto_filter is enabled and refresh invoices
        self.auto_filter = True
        self._onchange_trade_channel()

    def action_create(self):
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(_('Please select invoices to settle.'))

        settlement = self.env['marketplace.settlement'].create({
            'name': self.name,
            'marketplace_partner_id': self.marketplace_partner_id.id,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'trade_channel': self.trade_channel,
            'invoice_ids': [(6, 0, self.invoice_ids.ids)],
            'settlement_account_id': self.settlement_account_id.id if self.settlement_account_id else False,
        })
        settlement.action_create_settlement()

        # action_create_settlement on the model returns an action opening the created move
        action = settlement.action_create_settlement()

        # Build a warning message linking to Reconcile Models action
        reconcile_action = self.env.ref('marketplace_settlement.action_marketplace_reconcile')
        if reconcile_action:
            link = '/web#action=%d' % (reconcile_action.id,)
            warning_msg = _('Settlement created. You may want to reconcile fees: <a href="%s" target="_blank">Open Reconcile Models</a>') % link
        else:
            warning_msg = _('Settlement created.')

        # If the settlement returned an action (to open the move), attach a warning popup
        if isinstance(action, dict):
            action['warning'] = {
                'title': _('Settlement Created'),
                'message': warning_msg,
            }
            return action

        # fallback: open settlement form with a warning
        return {
            'type': 'ir.actions.act_window',
            'name': _('Marketplace Settlement'),
            'res_model': 'marketplace.settlement',
            'res_id': settlement.id,
            'view_mode': 'form',
            'target': 'current',
            'warning': {
                'title': _('Settlement Created'),
                'message': warning_msg,
            },
        }

    def action_refresh_invoices(self):
        """Manual action to refresh invoice list based on current trade channel"""
        self._onchange_trade_channel()
        return None
