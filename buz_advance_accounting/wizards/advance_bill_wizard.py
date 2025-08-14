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

    preview_line_ids = fields.One2many('purchase.advance.bill.preview.line', 'wizard_id', string='Preview Lines', readonly=True)

    @api.onchange('purchase_id')
    def _onchange_purchase(self):
        if self.purchase_id:
            # Set amount to include tax (total amount)
            self.amount = self.purchase_id.amount_total
            self.currency_id = self.purchase_id.currency_id
            self._recompute_preview()

    @api.onchange('amount', 'accrual_account_id', 'journal_id', 'date', 'ref')
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
            
            # Use the amount from wizard (which is the total amount including tax)
            total_amount = wizard.amount
            
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
            
            # Convert to company currency for accounting amounts
            amount_untaxed_company = src_currency._convert(amount_untaxed, company_currency, company, wizard.date or fields.Date.context_today(wizard))
            amount_tax_company = src_currency._convert(amount_tax, company_currency, company, wizard.date or fields.Date.context_today(wizard))
            
            payable_account = wizard._get_payable_account_from_partner(po.partner_id)
            expense_account = wizard._get_expense_account_from_po(po)
            
            # Get tax input account
            tax_input_account = wizard._get_tax_input_account(po)
            
            label = wizard.ref or _('Advance Accrual')
            label_tax = wizard.ref or _('Input Tax')
            
            if amount_untaxed_company > 0 and expense_account and wizard.accrual_account_id:
                # Expense line (Debit) - amount before tax
                lines.append((0, 0, {
                    'account_id': expense_account.id,
                    'name': label,
                    'debit': amount_untaxed_company,
                    'credit': 0.0,
                }))
                
                # Tax line (Debit) - if there's tax
                if amount_tax_company > 0 and tax_input_account:
                    lines.append((0, 0, {
                        'account_id': tax_input_account.id,
                        'name': label_tax,
                        'debit': amount_tax_company,
                        'credit': 0.0,
                    }))
                
                # Accrual account (Credit) - total amount (as entered by user)
                total_amount_company = src_currency._convert(total_amount, company_currency, company, wizard.date or fields.Date.context_today(wizard))
                lines.append((0, 0, {
                    'account_id': wizard.accrual_account_id.id,
                    'name': label,
                    'debit': 0.0,
                    'credit': total_amount_company,
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
        
        # Use the amount from wizard (which is the total amount including tax)
        total_amount = self.amount
        
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
        
        # Convert to company currency
        amount_untaxed_company = src_currency._convert(amount_untaxed, company_currency, company, self.date or fields.Date.context_today(self))
        amount_tax_company = src_currency._convert(amount_tax, company_currency, company, self.date or fields.Date.context_today(self))
        total_amount_company = src_currency._convert(total_amount, company_currency, company, self.date or fields.Date.context_today(self))

        # Prepare journal entry lines
        journal_lines = []
        
        # Expense line (Debit) - amount before tax
        journal_lines.append((0, 0, {
            'name': self.ref or _('Advance Accrual'),
            'debit': amount_untaxed_company if amount_untaxed_company > 0 else 0.0,
            'credit': 0.0,
            'account_id': expense_account.id,
            'partner_id': po.partner_id.id,
            'currency_id': src_currency.id,
            'amount_currency': amount_untaxed if src_currency != company_currency else amount_untaxed_company,
        }))
        
        # Tax line (Debit) - if there's tax and tax account
        if amount_tax_company > 0 and tax_input_account:
            journal_lines.append((0, 0, {
                'name': self.ref or _('Input Tax'),
                'debit': amount_tax_company,
                'credit': 0.0,
                'account_id': tax_input_account.id,
                'partner_id': po.partner_id.id,
                'currency_id': src_currency.id,
                'amount_currency': amount_tax if src_currency != company_currency else amount_tax_company,
            }))
        
        # Accrual account (Credit) - total amount as entered by user
        journal_lines.append((0, 0, {
            'name': self.ref or _('Advance Accrual'),
            'debit': 0.0,
            'credit': total_amount_company if total_amount_company > 0 else 0.0,
            'account_id': self.accrual_account_id.id,
            'partner_id': po.partner_id.id,
            'currency_id': src_currency.id,
            'amount_currency': -total_amount if src_currency != company_currency else -total_amount_company,
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
            'amount': total_amount,  # Store the total amount as entered by user
            'currency_id': self.currency_id.id,
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
