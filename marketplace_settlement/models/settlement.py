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
    trade_channel = fields.Selection([
        ('shopee', 'Shopee'), 
        ('lazada', 'Lazada'), 
        ('nocnoc', 'Noc Noc'), 
        ('tiktok', 'Tiktok'), 
        ('other', 'Other')
    ], string='Trade Channel', default='shopee')
    invoice_count = fields.Integer('Invoice Count', compute='_compute_invoice_count')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done')
    ], string='State', default='draft', compute='_compute_state', store=True)

    @api.depends('invoice_ids')
    def _compute_invoice_count(self):
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    @api.depends('move_id')
    def _compute_state(self):
        for record in self:
            record.state = 'done' if record.move_id else 'draft'

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
        if not self.invoice_ids:
            raise UserError(_('Please select invoices to settle.'))

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

        # marketplace aggregate line (opposite)
        if total_amount == 0.0:
            raise UserError(_('Total settlement amount is zero.'))

        lines.append((0, 0, {
            'name': self.name,
            'account_id': mp_account.id,
            'partner_id': self.marketplace_partner_id.id,
            'debit': total_amount if total_amount > 0 else 0.0,
            'credit': -total_amount if total_amount < 0 else 0.0,
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

        return True
