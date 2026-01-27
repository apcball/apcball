# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError


class ReverseAccrualWizard(models.TransientModel):
    _name = 'reverse.accrual.wizard'
    _description = 'Reverse All Accrual Entries Wizard'

    purchase_id = fields.Many2one('purchase.order', required=True, readonly=True)
    reversal_date = fields.Date(
        string='Reversal Date', 
        required=True, 
        default=fields.Date.context_today,
        help='Date for the reversal journal entries'
    )
    accrual_count = fields.Integer(
        string='Accrual Entries to Reverse',
        compute='_compute_accrual_count'
    )
    accrual_ids = fields.One2many(
        related='purchase_id.advance_accrual_ids',
        readonly=True
    )
    
    # Exchange rate fields for reversal
    exchange_rate = fields.Float(string='Exchange Rate (USD→THB)', digits=(12, 6), default=1.0,
                                  help='Exchange rate at reversal date. For example, 36.00 means 1 USD = 36.00 THB')
    show_currency_diff = fields.Boolean(string='Show Currency Difference', compute='_compute_show_currency_diff')
    currency_diff_amount = fields.Monetary(string='Currency Difference', currency_field='company_currency_id', 
                                            compute='_compute_currency_diff')
    company_currency_id = fields.Many2one('res.currency', related='purchase_id.company_id.currency_id', store=False)

    @api.depends('purchase_id')
    def _compute_accrual_count(self):
        for wizard in self:
            if wizard.purchase_id:
                wizard.accrual_count = len(wizard.purchase_id.advance_accrual_ids.filtered(
                    lambda a: a.state == 'posted'
                ))
            else:
                wizard.accrual_count = 0
    
    @api.depends('purchase_id')
    def _compute_show_currency_diff(self):
        for wizard in self:
            # Show currency diff fields if any accrual has exchange rate set
            wizard.show_currency_diff = any(
                accrual.exchange_rate > 0 for accrual in wizard.purchase_id.advance_accrual_ids.filtered(
                    lambda a: a.state == 'posted'
                )
            )
    
    @api.depends('exchange_rate', 'purchase_id')
    def _compute_currency_diff(self):
        for wizard in self:
            total_diff = 0.0
            for accrual in wizard.purchase_id.advance_accrual_ids.filtered(lambda a: a.state == 'posted'):
                if accrual.exchange_rate and accrual.amount:
                    # Calculate difference: (original THB at creation) - (THB at reversal rate)
                    original_thb = accrual.amount_thb or (accrual.amount * accrual.exchange_rate)
                    reversal_thb = accrual.amount * wizard.exchange_rate
                    diff = original_thb - reversal_thb
                    total_diff += diff
            wizard.currency_diff_amount = total_diff
    
    @api.onchange('reversal_date')
    def _onchange_reversal_date(self):
        # Auto-fetch exchange rate when date changes
        if self.reversal_date and self.purchase_id:
            usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
            thb_currency = self.env['res.currency'].search([('name', '=', 'THB')], limit=1)
            if usd_currency and thb_currency:
                rate = usd_currency._convert(1.0, thb_currency, self.env.company, self.reversal_date)
                self.exchange_rate = rate

    def action_reverse_all(self):
        """Reverse all accrual entries with the specified date"""
        self.ensure_one()
        
        if not self.purchase_id:
            raise UserError(_('No Purchase Order provided.'))
        
        if not self.reversal_date:
            raise UserError(_('Please specify a reversal date.'))
        
        accruals_to_reverse = self.purchase_id.advance_accrual_ids.filtered(
            lambda a: a.state == 'posted'
        )
        
        if not accruals_to_reverse:
            raise UserError(_('No accrual entries found to reverse.'))
        
        reversed_count = 0
        for accrual in accruals_to_reverse:
            if accrual.state != 'posted':
                continue
                
            if not accrual.move_id or accrual.move_id.state != 'posted':
                continue
            
            move = accrual.move_id
            
            # Calculate currency difference if exchange rate exists
            currency_diff = 0.0
            if accrual.exchange_rate and self.exchange_rate and accrual.amount:
                original_thb = accrual.amount_thb or (accrual.amount * accrual.exchange_rate)
                reversal_thb = accrual.amount * self.exchange_rate
                currency_diff = original_thb - reversal_thb
            
            # Create reversal move with specified date
            reversal_vals = {
                'move_type': 'entry',
                'date': self.reversal_date,
                'journal_id': move.journal_id.id,
                'ref': (move.ref or '') + _(' (Reversal)'),
                'partner_id': move.partner_id.id,
                'currency_id': move.currency_id.id,
                'line_ids': []
            }
            
            # Create reversed lines with custom exchange rate
            for line in move.line_ids:
                # Recalculate THB amounts using reversal exchange rate
                if self.exchange_rate and self.exchange_rate > 0 and line.amount_currency:
                    new_debit = abs(line.amount_currency) * self.exchange_rate if line.credit > 0 else 0.0
                    new_credit = abs(line.amount_currency) * self.exchange_rate if line.debit > 0 else 0.0
                else:
                    new_debit = line.credit
                    new_credit = line.debit
                
                line_vals = {
                    'name': line.name + _(' (Reversal)'),
                    'account_id': line.account_id.id,
                    'partner_id': line.partner_id.id if line.partner_id else False,
                    'debit': new_debit,
                    'credit': new_credit,
                    'currency_id': line.currency_id.id if line.currency_id else False,
                    'amount_currency': -line.amount_currency if line.amount_currency else 0.0,
                }
                reversal_vals['line_ids'].append((0, 0, line_vals))
            
            # Add currency difference line if exists
            if abs(currency_diff) > 0.01 and accrual.diff_account_id:
                diff_line_vals = {
                    'name': _('Currency Exchange Difference'),
                    'account_id': accrual.diff_account_id.id,
                    'partner_id': move.partner_id.id,
                    'debit': abs(currency_diff) if currency_diff < 0 else 0.0,
                    'credit': abs(currency_diff) if currency_diff > 0 else 0.0,
                    'currency_id': False,
                    'amount_currency': 0.0,
                }
                reversal_vals['line_ids'].append((0, 0, diff_line_vals))
            
            reversal = self.env['account.move'].create(reversal_vals)
            reversal.action_post()
            accrual.reversal_move_id = reversal.id
            accrual.state = 'reversed'
            reversed_count += 1
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Reversal Complete'),
                'message': _('%s accrual entries reversed on %s.') % (
                    reversed_count, 
                    self.reversal_date.strftime('%d/%m/%Y')
                ),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_cancel(self):
        """Cancel the wizard"""
        return {'type': 'ir.actions.act_window_close'}
