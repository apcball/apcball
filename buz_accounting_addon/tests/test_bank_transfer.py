from odoo.tests import common, tagged
from odoo.exceptions import UserError
from odoo import fields

@tagged('post_install', '-at_install')
class TestAccountBankTransfer(common.TransactionCase):

    def setUp(self):
        super(TestAccountBankTransfer, self).setUp()
        
        self.company = self.env.company
        
        # Create Journals
        self.bank_journal_1 = self.env['account.journal'].create({
            'name': 'Bank 1',
            'type': 'bank',
            'code': 'BNK1',
            'currency_id': self.company.currency_id.id,
        })
        self.bank_journal_2 = self.env['account.journal'].create({
            'name': 'Bank 2',
            'type': 'bank',
            'code': 'BNK2',
            'currency_id': self.company.currency_id.id,
        })

    def test_bank_transfer_flow(self):
        """ Test the bank transfer creation and confirmation """
        transfer = self.env['account.bank.transfer'].create({
            'journal_id': self.bank_journal_1.id,
            'destination_journal_id': self.bank_journal_2.id,
            'amount': 1000.0,
            'date': fields.Date.today(),
        })
        
        # Check initial state
        self.assertEqual(transfer.state, 'draft')
        
        # Confirm
        transfer.action_confirm()
        
        # Check state after confirm
        self.assertEqual(transfer.state, 'posted')
        self.assertTrue(transfer.payment_id, "Payment should be created")
        
        # Check Payment values
        payment = transfer.payment_id
        self.assertTrue(payment.is_internal_transfer)
        self.assertEqual(payment.journal_id, self.bank_journal_1)
        self.assertEqual(payment.destination_journal_id, self.bank_journal_2)
        self.assertEqual(payment.amount, 1000.0)
        self.assertEqual(payment.payment_type, 'outbound')
        
    def test_bank_transfer_constraints(self):
        """ Test constraints """
        # Same journal
        with self.assertRaises(UserError):
            transfer = self.env['account.bank.transfer'].create({
                'journal_id': self.bank_journal_1.id,
                'destination_journal_id': self.bank_journal_1.id,
                'amount': 1000.0,
            }).action_confirm()

        # Negative amount
        with self.assertRaises(UserError):
            transfer = self.env['account.bank.transfer'].create({
                'journal_id': self.bank_journal_1.id,
                'destination_journal_id': self.bank_journal_2.id,
                'amount': -100.0,
            }).action_confirm()
