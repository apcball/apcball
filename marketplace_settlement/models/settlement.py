from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero
from odoo.tools import float_compare


class MarketplaceSettlement(models.Model):
    _name = 'marketplace.settlement'
    _description = 'Marketplace Settlement'
    _order = 'date desc, name desc'

    name = fields.Char('Settlement Ref', required=True)
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner', required=True)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True)
    date = fields.Date('Date', required=True, default=fields.Date.context_today)
    invoice_ids = fields.Many2many('account.move', string='Invoices')
    move_id = fields.Many2one('account.move', string='Settlement Move')
    settlement_account_id = fields.Many2one('account.account', string='Settlement Account',
        help='Optional account to post the marketplace aggregate line to. If empty the marketplace partner receivable will be used.')
    # Deductions
    fee_amount = fields.Monetary('Marketplace Fee', currency_field='company_currency_id', help='Commission or fee charged by marketplace')
    fee_account_id = fields.Many2one('account.account', string='Fee Account',
                                   help='Expense account for marketplace fees (e.g., 6201 - Marketplace Commission)',
                                   domain="[('account_type', 'in', ['expense', 'asset_expense'])]")
    vat_on_fee_amount = fields.Monetary('VAT on Fee', currency_field='company_currency_id', help='VAT amount on marketplace fee')
    vat_account_id = fields.Many2one('account.account', string='VAT Account',
                                   help='VAT input tax account (e.g., 1310 - VAT Input Tax)',
                                   domain="[('account_type', 'in', ['asset_current', 'liability_current'])]")
    wht_amount = fields.Monetary('Withholding Tax (WHT)', currency_field='company_currency_id', help='Tax withheld at source')
    wht_account_id = fields.Many2one('account.account', string='WHT Account',
                                   help='Withholding tax payable account (e.g., 2170 - WHT Payable)',
                                   domain="[('account_type', '=', 'liability_current')]")
    company_currency_id = fields.Many2one('res.currency', string='Company Currency', compute='_compute_company_currency')
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'), 
        ('lazada', 'Lazada'), 
        ('nocnoc', 'Noc Noc'), 
        ('tiktok', 'Tiktok'), 
        ('other', 'Other')
    ], string='Trade Channel', default='shopee')
    invoice_count = fields.Integer('Invoice Count', compute='_compute_invoice_count')
    total_invoice_amount = fields.Monetary('Total Invoice Amount', currency_field='company_currency_id', compute='_compute_amounts')
    total_deductions = fields.Monetary('Total Deductions', currency_field='company_currency_id', compute='_compute_amounts')
    net_settlement_amount = fields.Monetary('Net Settlement Amount', currency_field='company_currency_id', compute='_compute_amounts')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('posted', 'Posted'),
        ('reversed', 'Reversed')
    ], string='State', default='draft', compute='_compute_state', store=True)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    @api.depends('invoice_ids', 'fee_amount', 'vat_on_fee_amount', 'wht_amount')
    def _compute_amounts(self):
        for record in self:
            total_invoice = 0.0
            for inv in record.invoice_ids:
                if inv.move_type == 'out_refund':
                    total_invoice -= abs(inv.amount_residual)
                else:
                    total_invoice += abs(inv.amount_residual)
            
            record.total_invoice_amount = total_invoice
            record.total_deductions = (record.fee_amount or 0.0) + (record.vat_on_fee_amount or 0.0) + (record.wht_amount or 0.0)
            record.net_settlement_amount = total_invoice - record.total_deductions

    def _compute_company_currency(self):
        for rec in self:
            rec.company_currency_id = rec.env.company.currency_id

    @api.depends('move_id')
    def _compute_state(self):
        for record in self:
            if not record.move_id:
                record.state = 'draft'
            elif record.move_id.state == 'posted':
                # Check if there's a reverse move
                reverse_moves = self.env['account.move'].search([
                    ('reversed_entry_id', '=', record.move_id.id),
                    ('state', '=', 'posted')
                ])
                if reverse_moves:
                    record.state = 'reversed'
                else:
                    record.state = 'posted'
            else:
                record.state = 'draft'

    def action_view_invoices(self):
        """Open related invoices"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.invoice_ids.ids)],
            'context': {'default_trade_channel': self.trade_channel},
        }

    def action_view_settlement_move(self):
        """Open settlement move"""
        self.ensure_one()
        if not self.move_id:
            return None
        return {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Move'),
            'res_model': 'account.move',
            'res_id': self.move_id.id,
            'view_mode': 'form',
        }

    def action_create_settlement(self):
        self.ensure_one()
        
        # Check if settlement is already created
        if self.move_id:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Settlement Move'),
                'res_model': 'account.move',
                'res_id': self.move_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        if not self.invoice_ids:
            raise UserError(_('Please select invoices to settle.'))

        # Validate deduction accounts if amounts are provided
        if self.fee_amount and not self.fee_account_id:
            raise UserError(_('Please specify Fee Account for marketplace fee.\n\nSuggested account codes:\n• 6201 - Marketplace Commission\n• 6210 - Sales Commission\n• 6xxx - Marketing/Sales Expenses'))
        if self.vat_on_fee_amount and not self.vat_account_id:
            raise UserError(_('Please specify VAT Account for VAT on fee.\n\nSuggested account codes:\n• 1310 - VAT Input Tax\n• 1311 - VAT Recoverable\n• 2xxx - VAT Payable (if applicable)'))
        if self.wht_amount and not self.wht_account_id:
            raise UserError(_('Please specify WHT Account for withholding tax.\n\nSuggested account codes:\n• 2170 - Withholding Tax Payable\n• 2171 - WHT 3% (Services)\n• 2172 - WHT 1% (Others)'))

        # prepare move lines
        lines = []
        total_amount = 0.0
        currency = self.invoice_ids[0].currency_id

        # helper to detect receivable account across Odoo versions
        def _is_receivable_account(account):
            if not account:
                return False
            # new style: account.user_type_id.type == 'receivable'
            if hasattr(account, 'user_type_id') and getattr(account.user_type_id, 'type', False):
                return account.user_type_id.type == 'receivable'
            # fallback: account.internal_type == 'receivable'
            if hasattr(account, 'internal_type'):
                return account.internal_type == 'receivable'
            # fallback: account.account_type_id.internal_type
            if hasattr(account, 'account_type_id') and getattr(account.account_type_id, 'internal_type', False):
                return account.account_type_id.internal_type == 'receivable'
            return False

        # Determine aggregate account for settlement:
        # 1) explicit settlement_account_id (preferred)
        # 2) journal default account (e.g., bank/cash account for the selected journal)
        # 3) marketplace partner receivable as a last resort
        mp_account = self.settlement_account_id or getattr(self.journal_id, 'default_account_id', False) or self.marketplace_partner_id.property_account_receivable_id
        if not mp_account:
            raise UserError(_('Please configure a settlement account on the settlement, a default account on the journal, or set a receivable account on the marketplace partner.'))

        # Prevent posting the marketplace aggregate to a receivable account by mistake.
        # This commonly causes both customer receivables and the aggregate to post to the
        # same account (as seen in your screenshot). Ask the user to select a proper
        # liquidity/bank account in the wizard or configure the journal default account.
        if _is_receivable_account(mp_account):
            raise UserError(_(
                'The settlement aggregate account (%s) is a receivable account.\n'
                'Please choose a bank/liquidity account as the settlement account in the wizard,\n'
                'or configure the selected journal with an appropriate default account.'
            ) % (mp_account.name,))

        for inv in self.invoice_ids:
            if inv.state != 'posted':
                raise UserError(_('Invoice %s must be posted.') % inv.name)
            # compute residual amount (amount due)
            residual = inv.amount_residual
            # support refunds (credit notes) with negative residual
            sign = 1
            if inv.move_type == 'out_refund':
                sign = -1
            amt = residual * sign
            if not float_is_zero(amt, precision_digits=2):
                total_amount += amt
                # credit/debit to customer's receivable
                cust_account = inv.partner_id.property_account_receivable_id
                if not cust_account:
                    raise UserError(_('Customer %s must have receivable account.') % inv.partner_id.name)
                # create line for that customer's receivable (reverse of invoice residual)
                lines.append((0, 0, {
                    'name': inv.name + ' - settlement',
                    'account_id': cust_account.id,
                    'partner_id': inv.partner_id.id,
                    'credit': amt if amt > 0 else 0.0,
                    'debit': -amt if amt < 0 else 0.0,
                }))

        # Add deduction lines
        total_deductions = 0.0
        
        # Marketplace Fee
        if self.fee_amount and not float_is_zero(self.fee_amount, precision_digits=2):
            lines.append((0, 0, {
                'name': _('Marketplace Fee - %s') % self.name,
                'account_id': self.fee_account_id.id,
                'partner_id': self.marketplace_partner_id.id,
                'debit': self.fee_amount,
                'credit': 0.0,
            }))
            total_deductions += self.fee_amount

        # VAT on Fee
        if self.vat_on_fee_amount and not float_is_zero(self.vat_on_fee_amount, precision_digits=2):
            lines.append((0, 0, {
                'name': _('VAT on Marketplace Fee - %s') % self.name,
                'account_id': self.vat_account_id.id,
                'partner_id': self.marketplace_partner_id.id,
                'debit': self.vat_on_fee_amount,
                'credit': 0.0,
            }))
            total_deductions += self.vat_on_fee_amount

        # Withholding Tax (WHT)
        if self.wht_amount and not float_is_zero(self.wht_amount, precision_digits=2):
            lines.append((0, 0, {
                'name': _('Withholding Tax - %s') % self.name,
                'account_id': self.wht_account_id.id,
                'partner_id': self.marketplace_partner_id.id,
                'debit': self.wht_amount,
                'credit': 0.0,
            }))
            total_deductions += self.wht_amount

        # Calculate net settlement amount (gross - deductions)
        net_settlement_amount = total_amount - total_deductions

        # marketplace aggregate line (opposite) - adjusted for deductions
        if total_amount == 0.0:
            raise UserError(_('Total settlement amount is zero.'))

        lines.append((0, 0, {
            'name': self.name,
            'account_id': mp_account.id,
            'partner_id': self.marketplace_partner_id.id,
            'debit': net_settlement_amount if net_settlement_amount > 0 else 0.0,
            'credit': -net_settlement_amount if net_settlement_amount < 0 else 0.0,
        }))

        move_vals = {
            'ref': self.name,
            'journal_id': self.journal_id.id,
            'date': self.date,
            'line_ids': lines,
        }
        move = self.env['account.move'].create(move_vals)
        # use action_post() to post moves (action name depends on Odoo version)
        if hasattr(move, 'action_post'):
            move.action_post()
        elif hasattr(move, 'post'):
            move.post()
        self.move_id = move.id

        # compute total in company currency to detect overall negative settlements
        company = self.env.company
        company_total = 0.0
        for inv in self.invoice_ids:
            # amount in invoice currency with sign
            sign = -1 if inv.move_type == 'out_refund' else 1
            amt = inv.amount_residual * sign
            # convert to company currency using invoice currency conversion helper
            curr = inv.currency_id or company.currency_id
            company_total += curr._convert(amt, company.currency_id, inv.company_id, self.date or fields.Date.context_today(self))

        # reconcile each invoice's receivable line with corresponding move line
        for inv in self.invoice_ids:
            # find invoice receivable line
            aml_inv = inv.line_ids.filtered(lambda l: _is_receivable_account(l.account_id) and (not float_is_zero(l.balance, precision_digits=2)))
            # find in settlement move corresponding partner line
            aml_set = move.line_ids.filtered(lambda l: l.partner_id == inv.partner_id and _is_receivable_account(l.account_id))
            # reconcile pairwise (only unreconciled lines)
            try:
                to_reconcile = (aml_inv + aml_set).filtered(lambda l: not l.reconciled)
                if to_reconcile:
                    to_reconcile.reconcile()
            except Exception:
                # best-effort: continue
                pass

        # return action opening the posted move with a banner link to reconcile models
        action = {
            'type': 'ir.actions.act_window',
            'name': _('Settlement Move'),
            'res_model': 'account.move',
            'res_id': move.id,
            'view_mode': 'form',
            'target': 'current',
        }

        # warn user if company-currency total is negative
        if company_total < 0:
            warning_msg = _(
                'Total settlement amount in company currency is negative (%.2f).\n'
                'This will result in a negative entry for the company and may need to be adjusted in a subsequent period.'
            ) % (company_total,)
            action['warning'] = {
                'title': _('Negative Settlement Total'),
                'message': warning_msg,
            }

        # attach a client action / notification by using context flags the view can pick up
        # Here we provide an action that the caller (wizard) can return directly as well.
        return action

    def action_reverse_settlement(self):
        """Reverse the settlement move and clear the link"""
        self.ensure_one()
        
        if not self.move_id:
            raise UserError(_('No settlement move to reverse.'))
            
        if self.state not in ['posted']:
            raise UserError(_('Can only reverse posted settlements.'))
            
        # Create reverse move
        reverse_move = self.move_id._reverse_moves([{
            'ref': _('Reverse of %s') % self.move_id.ref,
            'date': fields.Date.context_today(self),
        }])
        
        if reverse_move:
            # Post the reverse move
            reverse_move.action_post()
            
            # Clear the settlement link so it can be recreated
            old_move_id = self.move_id.id
            self.move_id = False
            
            # Return action to show both moves
            return {
                'type': 'ir.actions.act_window',
                'name': _('Settlement Reversed'),
                'res_model': 'account.move',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', [old_move_id, reverse_move.id])],
                'context': {
                    'default_ref': self.name,
                },
                'help': _(
                    '<p>Settlement has been reversed.</p>'
                    '<p>You can now create a new settlement with correct data.</p>'
                ),
            }
        else:
            raise UserError(_('Failed to create reverse move.'))
