
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class pettyCashSettlement(models.Model):
    _name = "petty.cash.settlement"
    _description = "Petty Cash Settlement"

    def _get_expense_account_domain(self):
        account_ids = self.env['account.account'].search([('account_type', '=', 'expense')])
        return [('id', 'in', account_ids and account_ids.ids or [])]

    name = fields.Char('Description', required=True, copy=False)
    bill_id = fields.Many2one('account.move', 'Vendor Bill', domain=[('move_type', '=', 'in_invoice'), ('state', '=', 'posted')], copy=False)
    expense_id = fields.Many2one('hr.expense.sheet', 'Expense Sheet', domain=[('state', '=', 'post')], copy=False)
    is_bill = fields.Boolean('Is Bill', default=False, store=True)
    is_expense = fields.Boolean('Is Expense', default=False, store=True)
    is_reconciled = fields.Boolean('Is reconciled', default=False, store=True)
    petty_request_id = fields.Many2one('petty.cash.request', 'Petty Cash Request', copy=False)
    expense_account_id = fields.Many2one('account.account', 'Expense Account', domain=_get_expense_account_domain)
    product_id = fields.Many2one('product.product', 'Product', copy=False, domain=[('can_be_expensed', '=', True)])
    amount = fields.Float('Amount', required=True)

    attachment_id = fields.Many2one('ir.attachment', string='Shared attachment')

    @api.onchange('bill_id')
    def _onchange_bill_id(self):
        if self.bill_id:
            if self.bill_id.payment_state != 'not_paid':
                self.bill_id = False
                return {'warning':
                    {
                        'title': _("Warning"),
                        'message': _('This bill is already reconciled or paid')
                    }
                }
            self.amount = self.bill_id.amount_total
            self.is_bill = True
            self.name = _('Settlement from vendor bill by No: %(name)s', name=self.bill_id.name)
        else:
            self.amount = False
            self.is_bill = False
            self.name = False

    @api.onchange('expense_id')
    def _onchange_expense_id(self):
        if self.expense_id:
            if self.expense_id.state != 'post':
                self.expense_id = False
                return {'warning':
                    {
                        'title': _("Warning"),
                        'message': _('This expense sheet is invalid to reconcile')
                    }
                }
            self.amount = self.expense_id.total_amount
            self.is_expense = True
            self.name = _('Settlement from expense sheet: %(name)s', name=self.expense_id.name)
        else:
            self.amount = False
            self.is_expense = False
            self.name = False

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id:
            if not self.name:
                self.name = self.product_id.display_name or ''
            # In Odoo 17 the price_compute method was removed. Use template's standard_price
            # or fall back to product fields (standard_price/list_price) if available.
            tmpl = getattr(self.product_id, 'product_tmpl_id', None)
            standard = False
            if tmpl:
                standard = getattr(tmpl, 'standard_price', False)
            if not standard:
                standard = getattr(self.product_id, 'standard_price', False)
            if not standard:
                standard = getattr(self.product_id, 'list_price', 0.0)
            self.amount = standard or 0.0
            account = self.product_id.product_tmpl_id._get_product_accounts()['expense']
            if account:
                self.expense_account_id = account

    def _set_is_reconcile(self):
        self.is_reconciled = True

    def _settlement_line_with_bill(self, petty):

        petty_account_id = petty.petty_cash_journal_id.default_account_id
        petty_suspense_account_id = petty.petty_cash_journal_id.suspense_account_id
        petty_requester_id = petty.requester_partner_id

        for settlement in self:
            move_line = settlement.bill_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable')

            adjustment_suspense_name = 'Reconcile the bill from ( %s )' % petty.narration

            line_ids_for_suspense = [
                (0, 0, petty._prepare_debit_data(adjustment_suspense_name, move_line.account_id, settlement.amount,
                                                settlement.bill_id.partner_id)),
                (0, 0, petty._prepare_credit_data(adjustment_suspense_name, petty_suspense_account_id, settlement.amount,
                                                 petty_requester_id))
            ]
            move_suspense_id = self.env['account.move'].create({
                'narration': adjustment_suspense_name,
                'ref': 'Petty Cash [ %s ]' % petty.name,
                'journal_id': petty.petty_cash_journal_id.id,
                'date': fields.Date.today(),
                'move_type': 'entry',
                'line_ids': line_ids_for_suspense
            })
            if move_suspense_id:
                move_suspense_id.action_post()
                petty._reconciliation(settlement.bill_id, move_suspense_id, move_line.account_id)

            adjustment_name = 'Settlements of (%s) from (%s)' % (petty.narration, settlement.bill_id.name)

            line_ids_for_petty = [
                (0, 0,
                 petty._prepare_debit_data(adjustment_name, petty.petty_cash_journal_id.suspense_account_id, settlement.amount,
                                          petty_requester_id)),
                (0, 0,
                 petty._prepare_credit_data(adjustment_name, petty.petty_cash_journal_id.default_account_id, settlement.amount,
                                           petty_requester_id))
            ]
            move_petty_id = self.env['account.move'].create({
                'narration': adjustment_name,
                'ref': 'Settlements of %s' % petty.name,
                'journal_id': petty.petty_cash_journal_id.id,
                'date': fields.Date.today(),
                'move_type': 'entry',
                'line_ids': line_ids_for_petty
            })
            if move_petty_id:
                move_petty_id.action_post()
                petty._reconciliation(petty.move_id, move_petty_id, petty_account_id)
                settlement._set_is_reconcile()
        return True

    def _settlement_line_with_expense(self, petty):

        petty_account_id = petty.petty_cash_journal_id.default_account_id
        petty_suspense_account_id = petty.petty_cash_journal_id.suspense_account_id
        petty_requester_id = petty.requester_partner_id


        for settlement in self:
            expense_move_id = settlement.expense_id.account_move_id
            move_line = expense_move_id.line_ids.filtered(
                lambda l: l.account_id.account_type == 'liability_payable')
            payable_partner = move_line[0].mapped('partner_id')
            payable_account = move_line[0].mapped('account_id')
            payable_amount = sum(move_line.mapped('credit'))

            adjustment_suspense_name = 'Reconcile the expense sheet from ( %s )' % petty.narration

            line_ids_for_suspense = [
                (0, 0, petty._prepare_debit_data(adjustment_suspense_name, payable_account, payable_amount,
                                                payable_partner)),
                (0, 0, petty._prepare_credit_data(adjustment_suspense_name, petty_suspense_account_id, settlement.amount,
                                                 petty_requester_id))
            ]
            move_suspense_id = self.env['account.move'].create({
                'narration': adjustment_suspense_name,
                'ref': 'Petty Cash [ %s ]' % petty.name,
                'journal_id': petty.petty_cash_journal_id.id,
                'date': fields.Date.today(),
                'move_type': 'entry',
                'line_ids': line_ids_for_suspense
            })
            if move_suspense_id:
                move_suspense_id.action_post()
                petty._reconciliation(expense_move_id, move_suspense_id, payable_account)

            adjustment_name = 'Settlements of (%s) from (%s)' % (petty.narration, settlement.expense_id.name)

            line_ids_for_petty = [
                (0, 0,
                 petty._prepare_debit_data(adjustment_name, petty.petty_cash_journal_id.suspense_account_id, settlement.amount,
                                          petty_requester_id)),
                (0, 0,
                 petty._prepare_credit_data(adjustment_name, petty.petty_cash_journal_id.default_account_id, settlement.amount,
                                           petty_requester_id))
            ]
            move_petty_id = self.env['account.move'].create({
                'narration': adjustment_name,
                'ref': 'Settlements of %s' % petty.name,
                'journal_id': petty.petty_cash_journal_id.id,
                'date': fields.Date.today(),
                'move_type': 'entry',
                'line_ids': line_ids_for_petty
            })
            if move_petty_id:
                move_petty_id.action_post()
                petty._reconciliation(petty.move_id, move_petty_id, petty_account_id)
                settlement._set_is_reconcile()
        return True

    def _settlement_line_without_bill(self, petty):

        petty_account_id = petty.petty_cash_journal_id.default_account_id
        petty_requester_id = petty.requester_partner_id

        petty_journal = petty.petty_cash_journal_id
        line_ids = []
        adjustment_name = 'Settlements of ( %s )' % petty.narration
        credit_amount = 0.0
        for settlement in self:
            credit_amount += settlement.amount
            line_ids.append((0, 0,
                             petty._prepare_debit_data(settlement.name, settlement.expense_account_id, settlement.amount,
                                                      petty_requester_id)))

        line_ids.append((0, 0,
                         petty._prepare_credit_data(adjustment_name, petty_journal.default_account_id, credit_amount,
                                                   petty_requester_id)))
        move_id = self.env['account.move'].create({
            'narration': 'Settlements of ( %s )' % petty.narration,
            'ref': 'Settlements of %s' % petty.name,
            'journal_id': petty_journal.id,
            'date': fields.Date.today(),
            'move_type': 'entry',
            'line_ids': line_ids
        })
        if move_id:
            move_id.action_post()
            petty._reconciliation(petty.move_id, move_id, petty_account_id)
            self._set_is_reconcile()
        return True