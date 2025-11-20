# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo import Command
from odoo.exceptions import UserError


class PurchaseAdvanceBillWizard(models.TransientModel):
    _name = 'purchase.advance.bill.wizard'
    _description = 'Create Advance Accrual from PO'

    purchase_id = fields.Many2one('purchase.order', required=True)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, domain="[('type', '=', 'general')]")
    accrual_account_id = fields.Many2one('account.account', string='Accrual Account', required=True, domain="[('deprecated', '=', False)]")
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    date = fields.Date(default=fields.Date.context_today)
    ref = fields.Char(string='Reference')
    
    # Exchange rate fields
    auto_exchange_rate = fields.Float(string='Auto Exchange Rate (Decimal)', readonly=True, digits=(12, 6))
    auto_exchange_rate_thb = fields.Float(string='Auto Rate (THB per Unit)', readonly=True, digits=(12, 6), compute='_compute_exchange_rate_thb')
    manual_exchange_rate = fields.Float(string='Manual Rate (THB per Unit)', digits=(12, 6))
    exchange_rate_diff_amount = fields.Float(string='Exchange Rate Difference', readonly=True, digits=(12, 2))
    use_manual_exchange_rate = fields.Boolean(string='Use Manual Exchange Rate', default=False)
    show_exchange_rate_section = fields.Boolean(string='Show Exchange Rate Section', compute='_compute_show_exchange_rate_section')
    source_currency_name = fields.Char(string='Source Currency', compute='_compute_currency_names')
    company_currency_name = fields.Char(string='Company Currency', compute='_compute_currency_names')

    preview_line_ids = fields.One2many('purchase.advance.bill.preview.line', 'wizard_id', string='Preview Lines', readonly=True)

    @api.onchange('purchase_id')
    def _onchange_purchase(self):
        if self.purchase_id:
            # Set amount to include tax (total amount)
            self.amount = self.purchase_id.amount_total
            self.currency_id = self.purchase_id.currency_id
            self._compute_exchange_rates()
            self._recompute_preview()

    @api.onchange('amount', 'accrual_account_id', 'journal_id', 'date', 'ref', 'use_manual_exchange_rate', 'manual_exchange_rate', 'currency_id')
    def _onchange_recompute_preview(self):
        self._compute_exchange_rates()
        self._recompute_preview()
    
    @api.depends('purchase_id', 'currency_id')
    def _compute_show_exchange_rate_section(self):
        """Compute whether to show exchange rate section"""
        for wizard in self:
            if wizard.purchase_id and wizard.currency_id:
                company_currency = wizard.purchase_id.company_id.currency_id
                wizard.show_exchange_rate_section = wizard.currency_id.id != company_currency.id
            else:
                wizard.show_exchange_rate_section = False

    @api.depends('auto_exchange_rate', 'currency_id', 'purchase_id')
    def _compute_exchange_rate_thb(self):
        """Convert auto exchange rate from decimal to THB per Unit format"""
        for wizard in self:
            if wizard.auto_exchange_rate and wizard.auto_exchange_rate != 0:
                # Convert from decimal format (e.g., 0.030861) to THB per Unit (e.g., 32.45)
                # decimal_rate = 1 / thb_per_unit, so thb_per_unit = 1 / decimal_rate
                wizard.auto_exchange_rate_thb = 1.0 / wizard.auto_exchange_rate
            else:
                wizard.auto_exchange_rate_thb = 1.0

    @api.depends('currency_id', 'purchase_id')
    def _compute_currency_names(self):
        """Get currency names for display"""
        for wizard in self:
            if wizard.purchase_id and wizard.currency_id:
                company_currency = wizard.purchase_id.company_id.currency_id
                wizard.source_currency_name = wizard.currency_id.name
                wizard.company_currency_name = company_currency.name
            else:
                wizard.source_currency_name = ''
                wizard.company_currency_name = ''

    def _compute_exchange_rates(self):
        """Compute auto and manual exchange rates and the difference
        
        Exchange rate format explanation:
        - auto_exchange_rate: Odoo's internal decimal format (e.g., 0.030861)
        - auto_exchange_rate_thb: THB per Unit format (e.g., 32.45 THB per 1 USD)
        - manual_exchange_rate: THB per Unit format for user input (e.g., 32.10 THB per 1 USD)
        """
        if self.purchase_id and self.currency_id:
            company = self.purchase_id.company_id
            company_currency = company.currency_id
            
            # Only compute if different currencies
            if self.currency_id != company_currency:
                # Get auto exchange rate from Odoo (in decimal format)
                self.auto_exchange_rate = self.currency_id._get_conversion_rate(
                    company_currency, self.currency_id, company, self.date or fields.Date.context_today(self)
                )
                
                # Set manual exchange rate to auto rate (converted to THB per Unit) if not set
                if not self.manual_exchange_rate:
                    if self.auto_exchange_rate and self.auto_exchange_rate != 0:
                        self.manual_exchange_rate = 1.0 / self.auto_exchange_rate
                    else:
                        self.manual_exchange_rate = 1.0
                
                # Calculate exchange rate difference
                if self.use_manual_exchange_rate and self.manual_exchange_rate:
                    # Convert amount using both rates
                    amount_company_auto = self.currency_id._convert(
                        self.amount, company_currency, company, self.date or fields.Date.context_today(self)
                    )
                    # manual_exchange_rate is THB per Unit (e.g., 32.10 means 32.10 THB = 1 USD)
                    # To convert from foreign currency to company currency, we divide by the rate
                    amount_company_manual = self.amount / self.manual_exchange_rate if self.manual_exchange_rate != 0 else 0
                    self.exchange_rate_diff_amount = amount_company_manual - amount_company_auto
                else:
                    self.exchange_rate_diff_amount = 0
            else:
                # Same currency, no exchange rate difference
                self.auto_exchange_rate = 1.0
                self.manual_exchange_rate = 1.0
                self.exchange_rate_diff_amount = 0

    def _get_payable_account_from_partner(self, partner):
        return partner.property_account_payable_id

    def _get_expense_account_from_po(self, po):
        """Get expense account from products in PO lines"""
        expense_account = False
        for line in po.order_line:
            if line.product_id:
                # Get expense account from product category
                if line.product_id.categ_id.property_account_expense_categ_id:
                    expense_account = line.product_id.categ_id.property_account_expense_categ_id
                    break
                # Fallback to product's own expense account
                elif line.product_id.property_account_expense_id:
                    expense_account = line.product_id.property_account_expense_id
                    break
        
        # If no expense account found from products, use company's default
        if not expense_account:
            expense_account = po.company_id.account_journal_purchase_id.default_account_id
            
        return expense_account

    def _get_tax_input_account(self, po):
        """Get tax input account for purchase taxes"""
        tax_account = False
        
        # Get tax account from purchase order lines
        for line in po.order_line:
            for tax in line.taxes_id:
                if tax.type_tax_use == 'purchase':
                    # Get the input tax account
                    tax_account = tax.invoice_repartition_line_ids.filtered(
                        lambda r: r.repartition_type == 'tax'
                    ).account_id
                    if tax_account:
                        break
            if tax_account:
                break
        
        # Fallback: search for typical input tax account
        if not tax_account:
            tax_account = self.env['account.account'].search([
                ('code', 'like', '15%'),  # Common input tax account code
                ('company_id', '=', po.company_id.id)
            ], limit=1)
            
        # Another fallback: search for any input tax related account
        if not tax_account:
            tax_account = self.env['account.account'].search([
                ('name', 'ilike', 'input'),
                ('name', 'ilike', 'tax'),
                ('company_id', '=', po.company_id.id)
            ], limit=1)
            
        return tax_account

    def _recompute_preview(self):
        """Generate preview of journal entry lines
        
        Journal Entry Structure:
        - Debit Expense Account: Bill amount (source currency) ÷ Manual Exchange Rate
        - Debit Tax Input Account: Tax amount (source currency) ÷ Manual Exchange Rate  
        - Credit Accrual Account: Full bill amount (source currency) ÷ Exchange Rate (manual or auto)
        - Debit/Credit Exchange Difference: Difference between manual and auto rates (if applicable)
        """
        for wizard in self:
            lines = []
            if not wizard.purchase_id or not wizard.accrual_account_id:
                wizard.preview_line_ids = [Command.clear()]
                continue
            po = wizard.purchase_id
            company = po.company_id
            company_currency = company.currency_id
            src_currency = wizard.currency_id or po.currency_id or company_currency
            
            # Use PO amounts directly (in source currency) - NOT wizard.amount which gets converted
            total_amount = po.amount_total
            
            # Calculate tax rate from PO to split the amount
            if po.amount_total > 0:
                tax_rate = po.amount_tax / po.amount_total
                untaxed_rate = po.amount_untaxed / po.amount_total
            else:
                tax_rate = 0
                untaxed_rate = 1
            
            # Split the total amount
            amount_untaxed = total_amount * untaxed_rate
            amount_tax = total_amount * tax_rate
            
            # Calculate amounts using MANUAL exchange rate (for debit side)
            if wizard.use_manual_exchange_rate and wizard.manual_exchange_rate and src_currency != company_currency:
                # Use manual exchange rate (THB per Unit format - divide by rate)
                amount_untaxed_company_manual = amount_untaxed / wizard.manual_exchange_rate
                amount_tax_company_manual = amount_tax / wizard.manual_exchange_rate
                total_amount_company_manual = total_amount / wizard.manual_exchange_rate
            else:
                # Use auto exchange rate
                amount_untaxed_company_manual = src_currency._convert(amount_untaxed, company_currency, company, wizard.date or fields.Date.context_today(wizard))
                amount_tax_company_manual = src_currency._convert(amount_tax, company_currency, company, wizard.date or fields.Date.context_today(wizard))
                total_amount_company_manual = src_currency._convert(total_amount, company_currency, company, wizard.date or fields.Date.context_today(wizard))
            
            expense_account = wizard._get_expense_account_from_po(po)
            
            # Get tax input account
            tax_input_account = wizard._get_tax_input_account(po)
            
            label = wizard.ref or _('Advance Accrual')
            label_tax = wizard.ref or _('Input Tax')
            
            if amount_untaxed_company_manual > 0 and expense_account and wizard.accrual_account_id:
                # Expense line (Debit) - using MANUAL exchange rate
                lines.append((0, 0, {
                    'account_id': expense_account.id,
                    'name': label,
                    'debit': amount_untaxed_company_manual,
                    'credit': 0.0,
                }))
                
                # Tax line (Debit) - using MANUAL exchange rate, if there's tax
                if amount_tax_company_manual > 0 and tax_input_account:
                    lines.append((0, 0, {
                        'account_id': tax_input_account.id,
                        'name': label_tax,
                        'debit': amount_tax_company_manual,
                        'credit': 0.0,
                    }))
                
                # Accrual account (Credit) - FULL bill amount using appropriate rate
                # When manual rate is used: credit is the MANUAL rate converted amount
                # This matches the debit side total
                lines.append((0, 0, {
                    'account_id': wizard.accrual_account_id.id,
                    'name': label,
                    'debit': 0.0,
                    'credit': total_amount_company_manual,
                }))
                
                # Exchange rate difference line (if applicable)
                if wizard.use_manual_exchange_rate and wizard.exchange_rate_diff_amount != 0 and src_currency != company_currency:
                    exchange_rate_diff_account = wizard.env['advance.accounting.config'].get_exchange_rate_diff_account()
                    if exchange_rate_diff_account:
                        if wizard.exchange_rate_diff_amount > 0:
                            # Positive difference: Debit exchange rate diff account
                            lines.append((0, 0, {
                                'account_id': exchange_rate_diff_account.id,
                                'name': _('Exchange Rate Difference'),
                                'debit': abs(wizard.exchange_rate_diff_amount),
                                'credit': 0.0,
                            }))
                        else:
                            # Negative difference: Credit exchange rate diff account
                            lines.append((0, 0, {
                                'account_id': exchange_rate_diff_account.id,
                                'name': _('Exchange Rate Difference'),
                                'debit': 0.0,
                                'credit': abs(wizard.exchange_rate_diff_amount),
                            }))
            
            wizard.preview_line_ids = [Command.clear()] + [Command.create(vals[2]) for vals in lines]

    def action_create(self):
        """Create journal entry with correct accounting
        
        Entry structure:
        - Debit Expense/Tax: Bill amounts ÷ Manual Exchange Rate
        - Credit Accrual: Full bill amount ÷ Manual Exchange Rate (matches debit total)
        - Debit/Credit Exchange Difference: Difference if manual rate differs from auto
        """
        self.ensure_one()
        po = self.purchase_id
        if not po:
            raise UserError(_('No Purchase Order provided.'))
        if not self.accrual_account_id:
            raise UserError(_('Please select an Accrual Account.'))

        expense_account = self._get_expense_account_from_po(po)
        if not expense_account:
            raise UserError(_('No expense account found for products in this Purchase Order.'))
        
        tax_input_account = self._get_tax_input_account(po)
            
        company = po.company_id
        company_currency = company.currency_id
        src_currency = self.currency_id or po.currency_id or company_currency
        
        # Use PO amounts directly (in source currency) - NOT wizard.amount which gets converted
        total_amount = po.amount_total
        if total_amount <= 0:
            raise UserError(_('Amount must be positive.'))
        
        # Calculate tax rate from PO to split the amount
        if po.amount_total > 0:
            tax_rate = po.amount_tax / po.amount_total
            untaxed_rate = po.amount_untaxed / po.amount_total
        else:
            tax_rate = 0
            untaxed_rate = 1
        
        # Split the total amount
        amount_untaxed = total_amount * untaxed_rate
        amount_tax = total_amount * tax_rate
        
        # Calculate amounts using MANUAL exchange rate (for debit side)
        if self.use_manual_exchange_rate and self.manual_exchange_rate and src_currency != company_currency:
            # Use manual exchange rate (THB per Unit format - divide by rate)
            amount_untaxed_company_manual = amount_untaxed / self.manual_exchange_rate
            amount_tax_company_manual = amount_tax / self.manual_exchange_rate
            total_amount_company_manual = total_amount / self.manual_exchange_rate
        else:
            # Use auto exchange rate
            amount_untaxed_company_manual = src_currency._convert(amount_untaxed, company_currency, company, self.date or fields.Date.context_today(self))
            amount_tax_company_manual = src_currency._convert(amount_tax, company_currency, company, self.date or fields.Date.context_today(self))
            total_amount_company_manual = src_currency._convert(total_amount, company_currency, company, self.date or fields.Date.context_today(self))

        # Prepare journal entry lines
        journal_lines = []
        
        # Expense line (Debit) - using MANUAL exchange rate
        journal_lines.append((0, 0, {
            'name': self.ref or _('Advance Accrual'),
            'debit': amount_untaxed_company_manual if amount_untaxed_company_manual > 0 else 0.0,
            'credit': 0.0,
            'account_id': expense_account.id,
            'partner_id': po.partner_id.id,
            'currency_id': src_currency.id,
            'amount_currency': amount_untaxed if src_currency != company_currency else amount_untaxed_company_manual,
        }))
        
        # Tax line (Debit) - using MANUAL exchange rate, if there's tax and tax account
        if amount_tax_company_manual > 0 and tax_input_account:
            journal_lines.append((0, 0, {
                'name': self.ref or _('Input Tax'),
                'debit': amount_tax_company_manual,
                'credit': 0.0,
                'account_id': tax_input_account.id,
                'partner_id': po.partner_id.id,
                'currency_id': src_currency.id,
                'amount_currency': amount_tax if src_currency != company_currency else amount_tax_company_manual,
            }))
        
        # Accrual account (Credit) - FULL bill amount
        # Credit matches the debit side total when using manual rate
        journal_lines.append((0, 0, {
            'name': self.ref or _('Advance Accrual'),
            'debit': 0.0,
            'credit': total_amount_company_manual if total_amount_company_manual > 0 else 0.0,
            'account_id': self.accrual_account_id.id,
            'partner_id': po.partner_id.id,
            'currency_id': src_currency.id,
            'amount_currency': -total_amount if src_currency != company_currency else -total_amount_company_manual,
        }))
        
        # Exchange rate difference line (if applicable)
        if self.use_manual_exchange_rate and self.exchange_rate_diff_amount != 0 and src_currency != company_currency:
            exchange_rate_diff_account = self.env['advance.accounting.config'].get_exchange_rate_diff_account()
            if exchange_rate_diff_account:
                if self.exchange_rate_diff_amount > 0:
                    # Positive difference: Debit exchange rate diff account
                    journal_lines.append((0, 0, {
                        'name': _('Exchange Rate Difference'),
                        'debit': abs(self.exchange_rate_diff_amount),
                        'credit': 0.0,
                        'account_id': exchange_rate_diff_account.id,
                        'partner_id': po.partner_id.id,
                    }))
                else:
                    # Negative difference: Credit exchange rate diff account
                    journal_lines.append((0, 0, {
                        'name': _('Exchange Rate Difference'),
                        'debit': 0.0,
                        'credit': abs(self.exchange_rate_diff_amount),
                        'account_id': exchange_rate_diff_account.id,
                        'partner_id': po.partner_id.id,
                    }))

        move_vals = {
            'move_type': 'entry',
            'date': self.date or fields.Date.context_today(self),
            'journal_id': self.journal_id.id,
            'ref': self.ref or (po.name + ' - ' + _('Advance Accrual')),
            'partner_id': po.partner_id.id,
            'currency_id': company_currency.id,
            'line_ids': journal_lines,
            'purchase_id': po.id,
        }
        move = self.env['account.move'].create(move_vals)
        move.action_post()
        accrual = self.env['purchase.advance.accrual'].create({
            'purchase_id': po.id,
            'move_id': move.id,
            'amount': total_amount,
            'currency_id': src_currency.id,
            'date': self.date,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }


class PurchaseAdvanceBillPreviewLine(models.TransientModel):
    _name = 'purchase.advance.bill.preview.line'
    _description = 'Preview Lines for Advance Accrual Wizard'

    wizard_id = fields.Many2one('purchase.advance.bill.wizard', required=True, ondelete='cascade')
    account_id = fields.Many2one('account.account', string='Account', required=True)
    name = fields.Char(string='Label')
    debit = fields.Monetary(currency_field='currency_id')
    credit = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='wizard_id.purchase_id.company_id.currency_id', store=False)
