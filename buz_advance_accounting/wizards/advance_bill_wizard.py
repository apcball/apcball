# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo import Command
from odoo.exceptions import UserError


class PurchaseAdvanceBillWizard(models.TransientModel):
    _name = 'purchase.advance.bill.wizard'
    _description = 'Create Advance Accrual from PO'

    purchase_id = fields.Many2one('purchase.order', required=True)
    available_bill_ids = fields.Many2many('account.move', string='Available Bills', compute='_compute_available_bills', store=False)
    vendor_bill_id = fields.Many2one('account.move', string='Linked Vendor Bill', 
                                      domain="[('id', 'in', available_bill_ids)]",
                                      help='Select vendor bill from which amount and exchange rate will be pulled')
    bill_count = fields.Integer(string='Bill Count', compute='_compute_available_bills', store=False)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True, domain="[('type', '=', 'general')]")
    accrual_account_id = fields.Many2one('account.account', string='Accrual Account', required=True, domain="[('deprecated', '=', False)]")
    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one('res.currency', required=True, default=lambda self: self.env.company.currency_id)
    date = fields.Date(default=fields.Date.context_today)
    ref = fields.Char(string='Reference')
    
    # Exchange rate fields
    exchange_rate = fields.Float(string='Exchange Rate (USD→THB)', digits=(12, 6), default=1.0, 
                                  help='Exchange rate from USD to THB. For example, 35.50 means 1 USD = 35.50 THB')
    amount_thb = fields.Monetary(string='Amount in THB', currency_field='company_currency_id', compute='_compute_amount_thb', store=True)
    company_currency_id = fields.Many2one('res.currency', related='purchase_id.company_id.currency_id', store=False)
    
    # Currency difference accounts (from company settings)
    currency_gain_account_id = fields.Many2one('account.account', string='Gain Account', 
                                                related='purchase_id.company_id.income_currency_exchange_account_id',
                                                help='Currency exchange gain account from company settings')
    currency_loss_account_id = fields.Many2one('account.account', string='Loss Account',
                                                related='purchase_id.company_id.expense_currency_exchange_account_id', 
                                                help='Currency exchange loss account from company settings')

    preview_line_ids = fields.One2many('purchase.advance.bill.preview.line', 'wizard_id', string='Preview Lines', readonly=True)

    @api.depends('purchase_id')
    def _compute_available_bills(self):
        """Find all posted vendor bills linked to this PO"""
        for wizard in self:
            if not wizard.purchase_id:
                wizard.available_bill_ids = False
                wizard.bill_count = 0
                continue
            
            po = wizard.purchase_id
            
            # Search for bills linked through invoice lines (proper Odoo way)
            bills = self.env['account.move'].search([
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted'),
                ('invoice_line_ids.purchase_line_id.order_id', '=', po.id)
            ], order='date desc, id desc')
            
            # Also check custom purchase_id field if it exists
            bills_custom = self.env['account.move'].search([
                ('purchase_id', '=', po.id),
                ('move_type', '=', 'in_invoice'),
                ('state', '=', 'posted')
            ], order='date desc, id desc')
            
            # Combine and remove duplicates
            all_bills = (bills | bills_custom)
            wizard.available_bill_ids = all_bills
            wizard.bill_count = len(all_bills)

    @api.depends('amount', 'exchange_rate')
    def _compute_amount_thb(self):
        for wizard in self:
            wizard.amount_thb = wizard.amount * wizard.exchange_rate
    
    @api.onchange('purchase_id')
    def _onchange_purchase(self):
        if self.purchase_id:
            po = self.purchase_id
            # Set currency first
            self.currency_id = po.currency_id or self.env.company.currency_id
            
            # Check if called from picking/receipt
            from_picking = self.env.context.get('from_picking', False)
            
            if from_picking and self.available_bill_ids:
                # Called from Receipt and bills are available: select first bill
                self.vendor_bill_id = self.available_bill_ids[0]
                # The onchange for vendor_bill_id will set amount and rate
            elif not from_picking:
                # Called from PO: clear bill selection and use PO amount
                self.vendor_bill_id = False
                self.amount = po.amount_total
                
                # Get exchange rate from system
                usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                thb_currency = self.env['res.currency'].search([('name', '=', 'THB')], limit=1)
                
                if usd_currency and thb_currency and self.currency_id == usd_currency:
                    # Get exchange rate from currency rate table for today
                    rate = usd_currency._convert(1.0, thb_currency, self.env.company, self.date or fields.Date.today())
                    self.exchange_rate = rate
                else:
                    self.exchange_rate = 1.0
            else:
                # Called from Receipt but no bills found: use PO amount
                self.vendor_bill_id = False
                self.amount = po.amount_total
                
                # Get exchange rate from system
                usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                thb_currency = self.env['res.currency'].search([('name', '=', 'THB')], limit=1)
                
                if usd_currency and thb_currency and self.currency_id == usd_currency:
                    rate = usd_currency._convert(1.0, thb_currency, self.env.company, self.date or fields.Date.today())
                    self.exchange_rate = rate
                else:
                    self.exchange_rate = 1.0
                
            self._recompute_preview()

    @api.onchange('vendor_bill_id')
    def _onchange_vendor_bill_id(self):
        """Update amount and exchange rate when vendor bill is selected"""
        if self.vendor_bill_id:
            vendor_bill = self.vendor_bill_id
            
            # Use amount from vendor bill
            self.amount = vendor_bill.amount_total
            
            # Use exchange rate from vendor bill (from exchange_currency_rate module)
            if hasattr(vendor_bill, 'is_exchange') and vendor_bill.is_exchange and hasattr(vendor_bill, 'rate') and vendor_bill.rate > 0:
                # Use manual exchange rate from bill (exchange_currency_rate module)
                self.exchange_rate = vendor_bill.rate
            else:
                # Get system rate from bill's currency conversion
                usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
                thb_currency = self.env['res.currency'].search([('name', '=', 'THB')], limit=1)
                
                if usd_currency and thb_currency and self.currency_id == usd_currency:
                    # Get exchange rate from currency rate table for bill's date (ใช้วันที่ของ bill เสมอ)
                    bill_date = vendor_bill.date if vendor_bill.date else fields.Date.context_today(self)
                    rate = usd_currency._convert(1.0, thb_currency, self.env.company, bill_date)
                    self.exchange_rate = rate
                else:
                    self.exchange_rate = 1.0
            
            self._recompute_preview()

    @api.onchange('date')
    def _onchange_date(self):
        """Update exchange rate when date is changed"""
        if self.date and self.currency_id and self.purchase_id:
            # Get exchange rate from system for the selected date
            usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
            thb_currency = self.env['res.currency'].search([('name', '=', 'THB')], limit=1)
            
            if usd_currency and thb_currency and self.currency_id == usd_currency:
                # Get the actual rate from currency rate table
                rate_record = self.env['res.currency.rate'].search([
                    ('currency_id', '=', usd_currency.id),
                    ('name', '<=', self.date),
                    ('company_id', 'in', [self.env.company.id, False])
                ], order='name desc', limit=1)
                
                if rate_record and rate_record.inverse_company_rate > 0:
                    # inverse_company_rate is "THB per Unit" (1 USD = X THB)
                    self.exchange_rate = rate_record.inverse_company_rate
                else:
                    # Fallback to _convert method
                    rate = usd_currency._convert(1.0, thb_currency, self.env.company, self.date)
                    self.exchange_rate = rate
            
            self._recompute_preview()

    @api.onchange('amount', 'accrual_account_id', 'journal_id', 'ref', 'exchange_rate')
    def _onchange_recompute_preview(self):
        self._recompute_preview()

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
        for wizard in self:
            lines = []
            if not wizard.purchase_id or not wizard.accrual_account_id or wizard.amount <= 0:
                wizard.preview_line_ids = [Command.clear()]
                continue
            po = wizard.purchase_id
            company = po.company_id
            company_currency = company.currency_id
            src_currency = wizard.currency_id or po.currency_id or company_currency
            
            # Use the amount from wizard (which is the total amount including tax in USD)
            total_amount_usd = wizard.amount
            
            # Calculate tax rate from PO to split the amount
            if po.amount_total > 0:
                tax_rate = po.amount_tax / po.amount_total
                untaxed_rate = po.amount_untaxed / po.amount_total
            else:
                tax_rate = 0
                untaxed_rate = 1
            
            # Split the USD amount
            amount_untaxed_usd = total_amount_usd * untaxed_rate
            amount_tax_usd = total_amount_usd * tax_rate
            
            # DEBIT side: Convert using rate from wizard (shown in UI)
            if wizard.exchange_rate and wizard.exchange_rate > 0:
                amount_untaxed_thb_debit = amount_untaxed_usd * wizard.exchange_rate
                amount_tax_thb_debit = amount_tax_usd * wizard.exchange_rate
                total_debit = amount_untaxed_thb_debit + amount_tax_thb_debit
            else:
                amount_untaxed_thb_debit = src_currency._convert(amount_untaxed_usd, company_currency, company, wizard.date or fields.Date.context_today(wizard))
                amount_tax_thb_debit = src_currency._convert(amount_tax_usd, company_currency, company, wizard.date or fields.Date.context_today(wizard))
                total_debit = amount_untaxed_thb_debit + amount_tax_thb_debit
            
            # CREDIT side: Use the SAME rate as DEBIT (wizard.exchange_rate)
            # to ensure consistency with what user sees in the preview
            if wizard.exchange_rate and wizard.exchange_rate > 0:
                total_amount_thb_credit = total_amount_usd * wizard.exchange_rate
            else:
                total_amount_thb_credit = src_currency._convert(total_amount_usd, company_currency, company, wizard.date or fields.Date.context_today(wizard))
            
            # Calculate currency difference (should be 0 when using same rate)
            currency_diff = total_debit - total_amount_thb_credit
            
            payable_account = wizard._get_payable_account_from_partner(po.partner_id)
            expense_account = wizard._get_expense_account_from_po(po)
            
            # Get tax input account
            tax_input_account = wizard._get_tax_input_account(po)
            
            label = wizard.ref or _('Advance Accrual')
            label_tax = wizard.ref or _('Input Tax')
            
            if amount_untaxed_thb_debit > 0 and expense_account and wizard.accrual_account_id:
                # Expense line (Debit) - using MANUAL rate from wizard
                lines.append((0, 0, {
                    'account_id': expense_account.id,
                    'name': label + ' (Manual Rate: %.6f)' % (wizard.exchange_rate or 0),
                    'debit': amount_untaxed_thb_debit,
                    'credit': 0.0,
                }))
                
                # Tax line (Debit) - if there's tax, using MANUAL rate from wizard
                if amount_tax_thb_debit > 0 and tax_input_account:
                    lines.append((0, 0, {
                        'account_id': tax_input_account.id,
                        'name': label_tax + ' (Manual Rate: %.6f)' % (wizard.exchange_rate or 0),
                        'debit': amount_tax_thb_debit,
                        'credit': 0.0,
                    }))
                
                # Accrual account (Credit) - using same rate as Debit
                lines.append((0, 0, {
                    'account_id': wizard.accrual_account_id.id,
                    'name': label + ' (Rate: %.6f)' % (wizard.exchange_rate or 0),
                    'debit': 0.0,
                    'credit': total_amount_thb_credit,
                }))
                
                # Currency difference line (if exists)
                if abs(currency_diff) > 0.01:
                    if currency_diff > 0:
                        # Debit > Credit = Loss (expense): need to credit loss account
                        if wizard.currency_loss_account_id:
                            lines.append((0, 0, {
                                'account_id': wizard.currency_loss_account_id.id,
                                'name': _('Currency Exchange Loss'),
                                'debit': 0.0,
                                'credit': abs(currency_diff),
                            }))
                    else:
                        # Credit > Debit = Gain (income): need to debit gain account
                        if wizard.currency_gain_account_id:
                            lines.append((0, 0, {
                                'account_id': wizard.currency_gain_account_id.id,
                                'name': _('Currency Exchange Gain'),
                                'debit': abs(currency_diff),
                                'credit': 0.0,
                            }))
            
            wizard.preview_line_ids = [Command.clear()] + [Command.create(vals[2]) for vals in lines]

    def action_create(self):
        self.ensure_one()
        po = self.purchase_id
        if not po:
            raise UserError(_('No Purchase Order provided.'))
        if self.amount <= 0:
            raise UserError(_('Amount must be positive.'))
        if not self.accrual_account_id:
            raise UserError(_('Please select an Accrual Account.'))

        expense_account = self._get_expense_account_from_po(po)
        if not expense_account:
            raise UserError(_('No expense account found for products in this Purchase Order.'))
        
        tax_input_account = self._get_tax_input_account(po)
            
        company = po.company_id
        company_currency = company.currency_id
        src_currency = self.currency_id or po.currency_id or company_currency
        
        # Use the amount from wizard (total amount including tax in USD)
        total_amount_usd = self.amount
        
        # Calculate tax rate from PO to split the amount
        if po.amount_total > 0:
            tax_rate = po.amount_tax / po.amount_total
            untaxed_rate = po.amount_untaxed / po.amount_total
        else:
            tax_rate = 0
            untaxed_rate = 1
        
        # Split the USD amount
        amount_untaxed_usd = total_amount_usd * untaxed_rate
        amount_tax_usd = total_amount_usd * tax_rate
        
        # DEBIT side: Convert using rate from wizard (shown in UI)
        if self.exchange_rate and self.exchange_rate > 0:
            amount_untaxed_thb_debit = amount_untaxed_usd * self.exchange_rate
            amount_tax_thb_debit = amount_tax_usd * self.exchange_rate
            total_debit = amount_untaxed_thb_debit + amount_tax_thb_debit
        else:
            # Fallback to system rate
            amount_untaxed_thb_debit = src_currency._convert(amount_untaxed_usd, company_currency, company, self.date or fields.Date.context_today(self))
            amount_tax_thb_debit = src_currency._convert(amount_tax_usd, company_currency, company, self.date or fields.Date.context_today(self))
            total_debit = amount_untaxed_thb_debit + amount_tax_thb_debit
        
        # CREDIT side: Use the SAME rate as DEBIT (self.exchange_rate)
        # to ensure consistency with what user sees in the preview
        if self.exchange_rate and self.exchange_rate > 0:
            total_amount_thb_credit = total_amount_usd * self.exchange_rate
        else:
            total_amount_thb_credit = src_currency._convert(total_amount_usd, company_currency, company, self.date or fields.Date.context_today(self))
        
        # Calculate currency difference (should be 0 when using same rate)
        currency_diff = total_debit - total_amount_thb_credit

        # Prepare journal entry lines
        journal_lines = []
        
        # Expense line (Debit) - using MANUAL rate from wizard
        journal_lines.append((0, 0, {
            'name': (self.ref or _('Advance Accrual')) + (' (Manual Rate: %.6f)' % (self.exchange_rate or 0)),
            'debit': amount_untaxed_thb_debit if amount_untaxed_thb_debit > 0 else 0.0,
            'credit': 0.0,
            'account_id': expense_account.id,
            'partner_id': po.partner_id.id,
            'currency_id': src_currency.id,
            'amount_currency': amount_untaxed_usd if src_currency != company_currency else amount_untaxed_thb_debit,
        }))
        
        # Tax line (Debit) - if there's tax and tax account, using MANUAL rate from wizard
        if amount_tax_thb_debit > 0 and tax_input_account:
            journal_lines.append((0, 0, {
                'name': (self.ref or _('Input Tax')) + (' (Manual Rate: %.6f)' % (self.exchange_rate or 0)),
                'debit': amount_tax_thb_debit,
                'credit': 0.0,
                'account_id': tax_input_account.id,
                'partner_id': po.partner_id.id,
                'currency_id': src_currency.id,
                'amount_currency': amount_tax_usd if src_currency != company_currency else amount_tax_thb_debit,
            }))
        
        # Accrual account (Credit) - using same rate as Debit
        journal_lines.append((0, 0, {
            'name': (self.ref or _('Advance Accrual')) + (' (Rate: %.6f)' % (self.exchange_rate or 0)),
            'debit': 0.0,
            'credit': total_amount_thb_credit if total_amount_thb_credit > 0 else 0.0,
            'account_id': self.accrual_account_id.id,
            'partner_id': po.partner_id.id,
            'currency_id': src_currency.id,
            'amount_currency': -total_amount_usd if src_currency != company_currency else -total_amount_thb_credit,
        }))
        
        # Handle currency difference using Default Accounts from Accounting settings
        if abs(currency_diff) > 0.01:
            # Get currency exchange accounts from company
            if currency_diff > 0:
                # Debit > Credit: Gain (need to credit)
                diff_account = company.expense_currency_exchange_account_id
                if not diff_account:
                    raise UserError(_('Currency difference detected (%.2f THB gain) but no "Loss Exchange Rate Account" is configured in Accounting Settings.') % abs(currency_diff))
                journal_lines.append((0, 0, {
                    'name': _('Currency Gain'),
                    'debit': 0.0,
                    'credit': abs(currency_diff),
                    'account_id': diff_account.id,
                    'partner_id': po.partner_id.id,
                    'currency_id': company_currency.id,
                }))
            else:
                # Credit > Debit: Loss (need to debit)
                diff_account = company.income_currency_exchange_account_id
                if not diff_account:
                    raise UserError(_('Currency difference detected (%.2f THB loss) but no "Gain Exchange Rate Account" is configured in Accounting Settings.') % abs(currency_diff))
                journal_lines.append((0, 0, {
                    'name': _('Currency Loss'),
                    'debit': abs(currency_diff),
                    'credit': 0.0,
                    'account_id': diff_account.id,
                    'partner_id': po.partner_id.id,
                    'currency_id': company_currency.id,
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
            'amount': total_amount_usd,  # Store USD amount
            'currency_id': self.currency_id.id,
            'date': self.date,
            'exchange_rate': self.exchange_rate,
            'amount_thb': total_debit,  # Store THB amount calculated with manual rate (Debit side)
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
