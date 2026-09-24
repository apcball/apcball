from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.addons.account.tests.common import AccountTestInvoicingCommon


@tagged('post_install', '-at_install')
class TestBankTransferFee(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.fee_account = cls.company_data['default_account_expense']
        cls.src = cls.company_data['default_journal_bank']
        cls.dst = cls.env['account.journal'].create({
            'name': 'Dest Bank', 'code': 'DBK', 'type': 'bank',
            'company_id': cls.company_data['company'].id,
        })
        cls.src.default_bank_charge_account_id = cls.fee_account

    def _transfer(self, amount=1000.0, fee=0.0):
        return self.env['account.bank.transfer'].create({
            'journal_id': self.src.id,
            'destination_journal_id': self.dst.id,
            'amount': amount,
            'bank_charge_amount': fee,
        })

    def _lines(self, move):
        return move.line_ids

    def test_no_fee_unchanged(self):
        t = self._transfer()
        t.action_confirm()
        self.assertEqual(len(t.payment_id.move_id.line_ids), 2)
        self.assertFalse(t.payment_id.move_id.line_ids.filtered(
            lambda l: l.account_id == self.fee_account))

    def test_fee_posted_on_source_leg_only(self):
        t = self._transfer(fee=30.0)
        t.action_confirm()
        src_move = t.payment_id.move_id
        fee_line = src_move.line_ids.filtered(lambda l: l.account_id == self.fee_account)
        self.assertEqual(fee_line.debit, 30.0)
        self.assertEqual(sum(src_move.line_ids.mapped('debit')), sum(src_move.line_ids.mapped('credit')))
        self.assertEqual(sum(src_move.line_ids.mapped('credit')), 1030.0)
        paired = t.payment_id.paired_internal_transfer_payment_id
        self.assertTrue(paired)
        self.assertFalse(paired.bank_charge_amount)
        self.assertEqual(sum(paired.move_id.line_ids.mapped('debit')), 1000.0)

    def test_missing_fee_account(self):
        self.src.default_bank_charge_account_id = False
        with self.assertRaises(UserError):
            self._transfer(fee=10.0).action_confirm()

    def test_negative_fee_rejected(self):
        with self.assertRaises(UserError):
            self._transfer(fee=-1.0).action_confirm()

    def test_draft_reverses_fee(self):
        t = self._transfer(fee=30.0)
        t.action_confirm()
        t.action_draft()
        self.assertEqual(t.state, 'draft')
        self.assertIn(t.payment_id.state, ('draft', 'cancel'))
