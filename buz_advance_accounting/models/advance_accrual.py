# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class PurchaseAdvanceAccrual(models.Model):
    _name = 'purchase.advance.accrual'
    _description = 'PO Advance Accrual Entry'
    _order = 'id desc'

    name = fields.Char(string='Reference', default=lambda self: _('PO Advance Accrual'))
    purchase_id = fields.Many2one('purchase.order', required=True, ondelete='cascade', index=True)
    move_id = fields.Many2one('account.move', string='Journal Entry', required=True, ondelete='cascade')
    amount = fields.Monetary(string='Accrued Amount', currency_field='currency_id', required=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    state = fields.Selection([
        ('posted', 'Posted'),
        ('reversed', 'Reversed'),
        ('arrived', 'Goods Arrived'),
    ], default='posted', required=True)
    reversal_move_id = fields.Many2one('account.move', string='Reversal Entry', ondelete='set null')
    date = fields.Date(default=fields.Date.context_today)
    
    # Foreign exchange tracking fields (for goods-in-transit)
    source_currency_amount = fields.Monetary(
        string='Amount in Source Currency',
        currency_field='currency_id',
        help='Amount in the original foreign currency (e.g. USD)'
    )
    exchange_rate_on_bill_date = fields.Float(
        string='Exchange Rate on Bill Date',
        digits=(12, 6),
        help='FX rate on the bill date (THB per source currency unit)'
    )
    amount_in_company_currency_on_bill = fields.Monetary(
        string='Amount in Company Currency on Bill Date',
        currency_field='company_currency_id',
        help='Amount converted to company currency using the bill date FX rate'
    )
    company_currency_id = fields.Many2one(
        'res.currency',
        related='purchase_id.company_id.currency_id',
        store=True,
        readonly=True
    )
    
    # Goods arrival tracking
    arrival_move_id = fields.Many2one(
        'account.move',
        string='Goods Arrival Reclassification Entry',
        ondelete='set null',
        help='JE posted when goods arrive for GIT to Inventory reclassification'
    )
    arrival_date = fields.Date(
        string='Goods Arrival Date',
        help='Date when goods physically arrived'
    )
    exchange_rate_on_arrival_date = fields.Float(
        string='Exchange Rate on Arrival Date',
        digits=(12, 6),
        help='FX rate on the arrival date (THB per source currency unit)'
    )
    amount_in_company_currency_on_arrival = fields.Monetary(
        string='Amount in Company Currency on Arrival',
        currency_field='company_currency_id',
        help='Amount converted to company currency using the arrival date FX rate'
    )
    fx_difference_amount = fields.Monetary(
        string='FX Difference Amount',
        currency_field='company_currency_id',
        help='FX gain or loss amount (positive=loss, negative=gain)'
    )
    is_git_entry = fields.Boolean(
        string='Is Goods-in-Transit Entry',
        default=False,
        help='True if this accrual entry includes goods-in-transit accounting'
    )
    stock_picking_id = fields.Many2one(
        'stock.picking',
        string='Related Stock Picking',
        ondelete='set null',
        help='Stock picking that triggers the goods arrival JE'
    )

    def action_reverse(self):
        for rec in self:
            if rec.state not in ('posted', 'arrived'):
                raise UserError(_('Only posted or arrived accruals can be reversed.'))
            if not rec.move_id or rec.move_id.state != 'posted':
                raise UserError(_('Related journal entry must be posted.'))
            
            move = rec.move_id
            # Create reversal move manually for better compatibility
            reversal_vals = {
                'move_type': 'entry',
                'date': fields.Date.context_today(self),
                'journal_id': move.journal_id.id,
                'ref': (move.ref or '') + _(' (Reversal)'),
                'partner_id': move.partner_id.id,
                'currency_id': move.currency_id.id,
                'line_ids': []
            }
            
            # Create reversed lines
            for line in move.line_ids:
                line_vals = {
                    'name': line.name + _(' (Reversal)'),
                    'account_id': line.account_id.id,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'debit': line.credit,  # Reverse debit/credit
                    'credit': line.debit,
                    'currency_id': line.currency_id.id if line.currency_id else False,
                    'amount_currency': -line.amount_currency if line.amount_currency else 0.0,
                }
                reversal_vals['line_ids'].append((0, 0, line_vals))
            
            reversal = self.env['account.move'].create(reversal_vals)
            reversal.action_post()
            rec.reversal_move_id = reversal.id
            rec.state = 'reversed'
        return True

    def _post_goods_in_transit_entry(self, journal_id, git_account_id, foreign_ap_account_id, date=None):
        """Post Goods-in-Transit (GIT) journal entry on bill date.
        
        Scenario:
        - Company currency: THB
        - Vendor currency: USD
        - On bill date, recognize the liability and goods-in-transit asset
        
        JE Structure:
        DR Goods in Transit (asset) = USD amount * FX rate on bill date
        CR Foreign AP Trade (liability) = USD amount * FX rate on bill date
        
        Args:
            journal_id: account.journal for posting
            git_account_id: account.account for Goods in Transit asset
            foreign_ap_account_id: account.account for Foreign AP liability
            date: Invoice/Bill date (defaults to today)
        
        Returns:
            account.move: Posted journal entry
        """
        self.ensure_one()
        
        if not journal_id:
            raise UserError(_('Please provide a Journal.'))
        if not git_account_id:
            raise UserError(_('Please provide a Goods in Transit Account.'))
        if not foreign_ap_account_id:
            raise UserError(_('Please provide a Foreign AP Trade Account.'))
        
        po = self.purchase_id
        company = po.company_id
        company_currency = company.currency_id
        source_currency = self.currency_id
        
        if date is None:
            date = self.date or fields.Date.context_today(self)
        
        # Get FX rate on bill date
        fx_rate = source_currency._get_conversion_rate(
            company_currency, source_currency, company, date
        )
        
        # Convert 1 unit of source currency to company currency
        # fx_rate is in Odoo's decimal format (e.g., 0.030861 for 1 USD = 32.45 THB)
        # To get THB per USD, we calculate 1 / fx_rate
        if fx_rate and fx_rate != 0:
            thb_per_unit = 1.0 / fx_rate
        else:
            thb_per_unit = 1.0
        
        # Amount in company currency on bill date
        amount_company_on_bill = source_currency._convert(
            self.amount,
            company_currency,
            company,
            date
        )
        
        # Prepare journal entry lines
        journal_lines = []
        
        # Line 1: Debit Goods in Transit
        journal_lines.append((0, 0, {
            'name': _('Goods in Transit - %s') % po.name,
            'debit': amount_company_on_bill if amount_company_on_bill > 0 else 0.0,
            'credit': 0.0,
            'account_id': git_account_id,
            'partner_id': po.partner_id.id,
            'currency_id': source_currency.id,
            'amount_currency': self.amount,
        }))
        
        # Line 2: Credit Foreign AP Trade
        journal_lines.append((0, 0, {
            'name': _('Foreign AP Trade - %s') % po.name,
            'debit': 0.0,
            'credit': amount_company_on_bill if amount_company_on_bill > 0 else 0.0,
            'account_id': foreign_ap_account_id,
            'partner_id': po.partner_id.id,
            'currency_id': source_currency.id,
            'amount_currency': -self.amount,
        }))
        
        # Create and post the journal entry
        move_vals = {
            'move_type': 'entry',
            'date': date,
            'journal_id': journal_id,
            'ref': _('GIT: %s') % po.name,
            'partner_id': po.partner_id.id,
            'currency_id': company_currency.id,
            'line_ids': journal_lines,
            'purchase_id': po.id,
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        # Store FX tracking data
        self.source_currency_amount = self.amount
        self.exchange_rate_on_bill_date = thb_per_unit
        self.amount_in_company_currency_on_bill = amount_company_on_bill
        self.is_git_entry = True
        self.move_id = move.id
        self.state = 'posted'
        
        return move

    def _post_goods_arrival_entry(self, journal_id, inventory_account_id, git_account_id, arrival_date=None):
        """Post Goods Arrival reclassification JE (GIT to Inventory + FX difference).
        
        Scenario:
        - Goods physically arrive after goods-in-transit period
        - Remove value from GIT using bill date FX rate
        - Add value to Inventory using arrival date FX rate
        - Book any exchange difference
        
        JE Structure:
        DR Inventory = USD amount * FX rate on arrival date
        CR Goods in Transit = USD amount * FX rate on bill date (historical rate)
        DR/CR Exchange Difference = difference if positive/negative
        
        Args:
            journal_id: account.journal for posting
            inventory_account_id: account.account for Inventory/Purchases
            git_account_id: account.account for Goods in Transit
            arrival_date: Date goods arrived (defaults to today)
        
        Returns:
            account.move: Posted journal entry
        """
        self.ensure_one()
        
        if not self.is_git_entry:
            raise UserError(_('This is not a Goods-in-Transit entry.'))
        
        if not journal_id:
            raise UserError(_('Please provide a Journal.'))
        if not inventory_account_id:
            raise UserError(_('Please provide an Inventory Account.'))
        if not git_account_id:
            raise UserError(_('Please provide a Goods in Transit Account.'))
        
        if not self.source_currency_amount:
            raise UserError(_('Source currency amount not found in the accrual entry.'))
        if not self.exchange_rate_on_bill_date:
            raise UserError(_('Exchange rate on bill date not found.'))
        if not self.amount_in_company_currency_on_bill:
            raise UserError(_('Amount in company currency on bill date not found.'))
        
        po = self.purchase_id
        company = po.company_id
        company_currency = company.currency_id
        source_currency = self.currency_id
        
        if arrival_date is None:
            arrival_date = fields.Date.context_today(self)
        
        # Step 1: Calculate THB credit from GIT (using original bill date rate)
        thb_credit_git = self.amount_in_company_currency_on_bill
        
        # Step 2: Get FX rate on arrival date
        fx_rate_arrival = source_currency._get_conversion_rate(
            company_currency, source_currency, company, arrival_date
        )
        
        if fx_rate_arrival and fx_rate_arrival != 0:
            thb_per_unit_arrival = 1.0 / fx_rate_arrival
        else:
            thb_per_unit_arrival = 1.0
        
        # Step 3: Calculate THB debit to Inventory (using arrival date rate)
        thb_debit_inventory = source_currency._convert(
            self.source_currency_amount,
            company_currency,
            company,
            arrival_date
        )
        
        # Step 4: Calculate FX difference
        fx_diff = thb_debit_inventory - thb_credit_git
        
        # Prepare journal entry lines
        journal_lines = []
        
        # Line 1: Debit Inventory/Purchases
        journal_lines.append((0, 0, {
            'name': _('Inventory Receipt - %s') % po.name,
            'debit': thb_debit_inventory if thb_debit_inventory > 0 else 0.0,
            'credit': 0.0,
            'account_id': inventory_account_id,
            'partner_id': po.partner_id.id,
            'currency_id': source_currency.id,
            'amount_currency': self.source_currency_amount,
        }))
        
        # Line 2: Credit Goods in Transit
        journal_lines.append((0, 0, {
            'name': _('Goods in Transit Credit - %s') % po.name,
            'debit': 0.0,
            'credit': thb_credit_git if thb_credit_git > 0 else 0.0,
            'account_id': git_account_id,
            'partner_id': po.partner_id.id,
            'currency_id': source_currency.id,
            'amount_currency': -self.source_currency_amount,
        }))
        
        # Line 3: FX Difference (only if fx_diff != 0)
        if abs(fx_diff) > 0.01:  # Allow for rounding differences
            config = self.env['advance.accounting.config'].get_config()
            exchange_rate_diff_account = config.exchange_rate_diff_account_id
            
            if not exchange_rate_diff_account:
                raise UserError(_('Exchange Rate Difference Account is not configured.'))
            
            if fx_diff > 0:
                # Positive difference: FX loss (Debit Exchange Difference)
                journal_lines.append((0, 0, {
                    'name': _('Exchange Rate Loss'),
                    'debit': abs(fx_diff),
                    'credit': 0.0,
                    'account_id': exchange_rate_diff_account.id,
                    'partner_id': False,
                }))
            else:
                # Negative difference: FX gain (Credit Exchange Difference)
                journal_lines.append((0, 0, {
                    'name': _('Exchange Rate Gain'),
                    'debit': 0.0,
                    'credit': abs(fx_diff),
                    'account_id': exchange_rate_diff_account.id,
                    'partner_id': False,
                }))
        
        # Create and post the journal entry
        move_vals = {
            'move_type': 'entry',
            'date': arrival_date,
            'journal_id': journal_id,
            'ref': _('GIT Arrival: %s') % po.name,
            'partner_id': po.partner_id.id,
            'currency_id': company_currency.id,
            'line_ids': journal_lines,
            'purchase_id': po.id,
        }
        
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        
        # Update accrual record with arrival data
        self.arrival_move_id = move.id
        self.arrival_date = arrival_date
        self.exchange_rate_on_arrival_date = thb_per_unit_arrival
        self.amount_in_company_currency_on_arrival = thb_debit_inventory
        self.fx_difference_amount = fx_diff
        self.state = 'arrived'
        
        return move
