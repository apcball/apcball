from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_is_zero
from odoo.tools import float_compare


class MarketplaceSettlement(models.Model):
    _name = 'marketplace.settlement'
    _description = 'Marketplace Settlement'

    name = fields.Char('Settlement Ref', required=True)
    marketplace_partner_id = fields.Many2one('res.partner', string='Marketplace Partner', required=True)
    journal_id = fields.Many2one('account.journal', string='Journal', required=True)
    date = fields.Date('Date', required=True)
    invoice_ids = fields.Many2many('account.move', string='Invoices')
    move_id = fields.Many2one('account.move', string='Settlement Move')
    trade_channel = fields.Selection([('shopee', 'Shopee'), ('lazada', 'Lazada'), ('nocnoc', 'Noc Noc'), ('tiktok', 'Tiktok'), ('other', 'Other')], string='Trade Channel', default='shopee')

    def action_create_settlement(self):
        self.ensure_one()
        if not self.invoice_ids:
            raise UserError(_('Please select invoices to settle.'))

        # prepare move lines
        lines = []
        total_amount = 0.0
        currency = self.invoice_ids[0].currency_id

        # marketplace receivable account: use partner property_account_receivable
        mp_account = self.marketplace_partner_id.property_account_receivable_id
        if not mp_account:
            raise UserError(_('Marketplace partner must have Receivable account defined.'))

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
