# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseGoodsArrivalWizard(models.TransientModel):
    _name = 'purchase.goods.arrival.wizard'
    _description = 'Post Goods Arrival Reclassification Entry'

    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Stock Picking',
        required=True,
        readonly=True
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        required=True,
        readonly=True
    )
    accrual_id = fields.Many2one(
        'purchase.advance.accrual',
        string='GIT Accrual Entry to Process',
        required=True,
        domain="[('purchase_id', '=', purchase_order_id), ('is_git_entry', '=', True), ('state', '=', 'posted')]",
        help='Select the Goods-in-Transit accrual entry to reclassify'
    )
    journal_id = fields.Many2one(
        'account.journal',
        string='Journal',
        required=True,
        domain="[('type', '=', 'general')]"
    )
    inventory_account_id = fields.Many2one(
        'account.account',
        string='Inventory/Purchases Account',
        required=True,
        domain="[('deprecated', '=', False)]",
        help='Account to receive the inventory when goods arrive'
    )
    git_account_id = fields.Many2one(
        'account.account',
        string='Goods-in-Transit Account',
        required=True,
        domain="[('deprecated', '=', False)]",
        help='Account that was used for the GIT posting'
    )
    arrival_date = fields.Date(
        string='Goods Arrival Date',
        required=True,
        default=fields.Date.context_today,
        help='Date when goods physically arrived'
    )
    ref = fields.Char(
        string='Reference',
        help='Reference/Description for the journal entry'
    )
    
    # Computed fields for preview (must come first for Monetary currency_field)
    currency_id = fields.Many2one(
        related='accrual_id.currency_id',
        readonly=True
    )
    company_currency_id = fields.Many2one(
        related='accrual_id.company_currency_id',
        readonly=True
    )
    
    # Display information
    source_currency_amount = fields.Monetary(
        related='accrual_id.source_currency_amount',
        readonly=True,
        currency_field='currency_id'
    )
    bill_date = fields.Date(
        related='accrual_id.date',
        readonly=True,
        string='Bill Date'
    )
    bill_fx_rate = fields.Float(
        related='accrual_id.exchange_rate_on_bill_date',
        readonly=True,
        string='FX Rate on Bill Date'
    )
    bill_amount_thb = fields.Monetary(
        related='accrual_id.amount_in_company_currency_on_bill',
        readonly=True,
        currency_field='company_currency_id',
        string='Amount in THB on Bill Date'
    )
    source_currency_name = fields.Char(
        related='accrual_id.currency_id.name',
        readonly=True
    )
    company_currency_name = fields.Char(
        related='accrual_id.company_currency_id.name',
        readonly=True
    )
    
    preview_line_ids = fields.One2many(
        'purchase.goods.arrival.preview.line',
        'wizard_id',
        string='Preview Lines',
        readonly=True
    )

    @api.onchange('accrual_id')
    def _onchange_accrual(self):
        """Set default journal when accrual is selected"""
        if self.accrual_id:
            # Try to get the journal from the original accrual entry
            if self.accrual_id.move_id and self.accrual_id.move_id.journal_id:
                self.journal_id = self.accrual_id.move_id.journal_id.id
            elif not self.journal_id:
                # Default to first available general journal
                default_journal = self.env['account.journal'].search(
                    [('type', '=', 'general')], limit=1
                )
                if default_journal:
                    self.journal_id = default_journal.id

    @api.onchange('arrival_date', 'accrual_id')
    def _onchange_recompute_preview(self):
        """Recompute preview when arrival date or accrual changes"""
        self._recompute_preview()

    def _recompute_preview(self):
        """Generate preview of goods arrival journal entry lines"""
        for wizard in self:
            lines = []
            
            if not wizard.accrual_id:
                wizard.preview_line_ids = [(5, 0, 0)]
                continue
            
            accrual = wizard.accrual_id
            if not accrual.is_git_entry or not accrual.source_currency_amount:
                wizard.preview_line_ids = [(5, 0, 0)]
                continue
            
            po = accrual.purchase_id
            company = po.company_id
            company_currency = company.currency_id
            source_currency = accrual.currency_id
            
            # Calculate amounts for arrival date
            amount_arrival_company = source_currency._convert(
                accrual.source_currency_amount,
                company_currency,
                company,
                wizard.arrival_date or fields.Date.context_today(wizard)
            )
            
            amount_git_credit = accrual.amount_in_company_currency_on_bill
            fx_diff = amount_arrival_company - amount_git_credit
            
            label = wizard.ref or _('Goods Arrival Reclassification')
            
            # Line 1: Debit Inventory
            if wizard.inventory_account_id and amount_arrival_company > 0:
                lines.append((0, 0, {
                    'account_id': wizard.inventory_account_id.id,
                    'name': label,
                    'debit': amount_arrival_company,
                    'credit': 0.0,
                }))
            
            # Line 2: Credit Goods in Transit
            if wizard.git_account_id and amount_git_credit > 0:
                lines.append((0, 0, {
                    'account_id': wizard.git_account_id.id,
                    'name': label,
                    'debit': 0.0,
                    'credit': amount_git_credit,
                }))
            
            # Line 3: FX Difference (if applicable)
            if abs(fx_diff) > 0.01:
                config = wizard.env['advance.accounting.config'].get_config()
                exchange_rate_diff_account = config.exchange_rate_diff_account_id
                
                if exchange_rate_diff_account:
                    if fx_diff > 0:
                        # Loss (Debit)
                        lines.append((0, 0, {
                            'account_id': exchange_rate_diff_account.id,
                            'name': _('Exchange Rate Loss'),
                            'debit': abs(fx_diff),
                            'credit': 0.0,
                        }))
                    else:
                        # Gain (Credit)
                        lines.append((0, 0, {
                            'account_id': exchange_rate_diff_account.id,
                            'name': _('Exchange Rate Gain'),
                            'debit': 0.0,
                            'credit': abs(fx_diff),
                        }))
            
            wizard.preview_line_ids = [(5, 0, 0)] + [(0, 0, vals) for vals in lines]

    def action_create(self):
        """Create the goods arrival reclassification journal entry"""
        self.ensure_one()
        
        if not self.accrual_id:
            raise UserError(_('Please select a GIT Accrual Entry.'))
        if not self.journal_id:
            raise UserError(_('Please select a Journal.'))
        if not self.inventory_account_id:
            raise UserError(_('Please select an Inventory Account.'))
        if not self.git_account_id:
            raise UserError(_('Please select a Goods-in-Transit Account.'))
        
        accrual = self.accrual_id
        
        if not accrual.is_git_entry:
            raise UserError(_('Selected accrual is not a Goods-in-Transit entry.'))
        if accrual.state != 'posted':
            raise UserError(_('Selected accrual entry must be in posted state.'))
        
        # Call the accrual method to post the arrival JE
        move = accrual._post_goods_arrival_entry(
            journal_id=self.journal_id.id,
            inventory_account_id=self.inventory_account_id.id,
            git_account_id=self.git_account_id.id,
            arrival_date=self.arrival_date or fields.Date.context_today(self)
        )
        
        # Link the stock picking
        if self.stock_picking_id:
            accrual.stock_picking_id = self.stock_picking_id.id
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }


class PurchaseGoodsArrivalPreviewLine(models.TransientModel):
    _name = 'purchase.goods.arrival.preview.line'
    _description = 'Preview Lines for Goods Arrival Wizard'

    wizard_id = fields.Many2one(
        'purchase.goods.arrival.wizard',
        required=True,
        ondelete='cascade'
    )
    account_id = fields.Many2one('account.account', string='Account', required=True)
    name = fields.Char(string='Label')
    debit = fields.Monetary(currency_field='currency_id')
    credit = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(
        related='wizard_id.company_currency_id',
        store=False
    )
