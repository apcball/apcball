
import logging

from odoo import api, fields, models, _
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class pettyCashOperations(models.TransientModel):
    _name = "petty.cash.operations"
    _description = "Petty Cash Operations"

    def _get_operation_journal_domain(self):
        petty_cash_journal_id = self.env.ref('petty_cash.petty_cash_journal', raise_if_not_found=False)
        if petty_cash_journal_id:
            petty_cash_journal_id = petty_cash_journal_id.id
        return [('type', 'in', ('bank', 'cash')), ('id', '!=', petty_cash_journal_id)]

    petty_request_id = fields.Many2one('petty.cash.request', 'Petty Cash Request', copy=False)
    requester_partner_id = fields.Many2one('res.partner', related='petty_request_id.requester_partner_id')
    operation_account_id = fields.Many2one('account.account', 'Operation Account', default=lambda self: self.env.company.account_journal_suspense_account_id)
    operation_journal_id = fields.Many2one('account.journal', 'Operation Journal', domain=_get_operation_journal_domain)
    amount = fields.Float('Petty Cash Amount', required=True)
    is_return = fields.Boolean(default=False)
    is_intemperance = fields.Boolean(default=False)

    @api.onchange('operation_journal_id')
    def _onchange_operation_journal(self):
        """When the operation journal is changed, set the operation account
        to the journal's default account (if any)."""
        for rec in self:
            if rec.operation_journal_id:
                rec.operation_account_id = rec.operation_journal_id.default_account_id
            else:
                rec.operation_account_id = False

    def action_paid(self):
        # Use the selected operation_account_id (not the journal's default account)
        operation_account = self.operation_account_id or self.operation_journal_id.default_account_id
        self.petty_request_id.move_id.write({
            'line_ids': self.petty_request_id._prepare_move_lines_data(operation_account, self.amount)
        })
        self.petty_request_id.move_id.action_post()
        self.petty_request_id.state = 'complete'
        self.petty_request_id.write({
            'state': 'complete',
            'operation_journal_id': self.operation_journal_id.id,
            'operation_account_id': self.operation_account_id.id,
        })
        return True

    def return_remaining_petty_cash(self):
        petty_account_id = self.petty_request_id.petty_cash_journal_id.default_account_id
        # prefer explicit selected operation account, fallback to journal default
        return_account_id = self.operation_account_id or self.operation_journal_id.default_account_id

        adjustment_name = 'Return The Remaining of ( %s )' % self.petty_request_id.narration

        line_ids = [
            (0, 0, self.petty_request_id._prepare_debit_data(adjustment_name, return_account_id, self.amount, self.requester_partner_id)),
            (0, 0, self.petty_request_id._prepare_credit_data(adjustment_name, petty_account_id, self.amount, self.requester_partner_id))
        ]
        move_id = self.env['account.move'].create({
            'narration': 'Return The Remaining of ( %s )' % self.petty_request_id.narration,
            'ref': 'Return The Remaining of %s' % self.petty_request_id.name,
            'journal_id': self.petty_request_id.petty_cash_journal_id.id,
            'date': fields.Date.today(),
            'move_type': 'entry',
            'line_ids': line_ids
        })
        if move_id:
            move_id.action_post()
            self.petty_request_id._reconciliation(self.petty_request_id.move_id, move_id, petty_account_id)
        settelement = self.env['petty.cash.settlement'].create({
            'name': adjustment_name,
            'is_reconciled': True,
            'amount': self.amount
        })
        self.petty_request_id.write({'settlement_ids': [(4, settelement.id)]})
        return True

    def intemperance_petty_cash(self):
        petty_account_id = self.petty_request_id.petty_cash_journal_id.default_account_id
        # prefer explicit selected operation account, fallback to journal default
        intemperance_account_id = self.operation_account_id or self.operation_journal_id.default_account_id

        adjustment_name = 'Settlement of intemperance amount of ( %s )' % self.petty_request_id.narration

        line_ids = [
            (0, 0, self.petty_request_id._prepare_debit_data(adjustment_name, petty_account_id, -self.amount, self.requester_partner_id)),
            (0, 0, self.petty_request_id._prepare_credit_data(adjustment_name, intemperance_account_id, -self.amount, self.requester_partner_id))
        ]
        move_id = self.env['account.move'].create({
            'narration': adjustment_name,
            'ref': 'intemperance amount of %s' % self.petty_request_id.name,
            'journal_id': self.petty_request_id.petty_cash_journal_id.id,
            'date': fields.Date.today(),
            'move_type': 'entry',
            'line_ids': line_ids
        })
        if move_id:
            move_id.action_post()
        settelement = self.env['petty.cash.settlement'].create({
            'name': adjustment_name,
            'is_reconciled': True,
            'amount': self.amount
        })
        self.petty_request_id.write({'settlement_ids': [(4, settelement.id)]})
        return True