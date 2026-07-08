from odoo.tests import common, tagged
from odoo.exceptions import UserError
from odoo import fields

@tagged('post_install', '-at_install')
class TestAccountBankTransfer(common.TransactionCase):

    def setUp(self):
        super(TestAccountBankTransfer, self).setUp()
        
        self.company = self.env.company
        
        # Create Journals — use unique codes to avoid collision with MOG_DEV data
        import uuid
        self.bank_journal_1 = self.env['account.journal'].create({
            'name': 'Test Bank 1',
            'type': 'bank',
            'code': 'TBT' + uuid.uuid4().hex[:3].upper(),
            'currency_id': self.company.currency_id.id,
        })
        self.bank_journal_2 = self.env['account.journal'].create({
            'name': 'Test Bank 2',
            'type': 'bank',
            'code': 'TBT' + uuid.uuid4().hex[:3].upper(),
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

    def test_bank_transfer_amount_defaults_from_voucher(self):
        """Inline bank transfer creation should inherit voucher net amount."""
        vendor = self.env['res.partner'].create({
            'name': 'Voucher Vendor',
            'supplier_rank': 1,
        })
        voucher = self.env['account.payment.voucher'].create({
            'partner_id': vendor.id,
            'date': fields.Date.today(),
            'destination_journal_id': self.bank_journal_1.id,
            'line_ids': [(0, 0, {
                'amount_to_pay_gross': 1250.0,
                'wht_base_amount': 0.0,
            })],
        })

        transfer = self.env['account.bank.transfer'].with_context(
            default_buz_payment_voucher_id=voucher.id,
        ).new({
            'journal_id': self.bank_journal_1.id,
            'destination_journal_id': self.bank_journal_2.id,
        })

        self.assertEqual(transfer.amount, 1250.0)

    def test_voucher_net_amount_follows_bank_transfer_when_no_lines(self):
        """Voucher net amount should reflect the bank transfer amount when there are no bill lines."""
        vendor = self.env['res.partner'].create({
            'name': 'Transfer Only Vendor',
            'supplier_rank': 1,
        })
        voucher = self.env['account.payment.voucher'].create({
            'partner_id': vendor.id,
            'date': fields.Date.today(),
            'destination_journal_id': self.bank_journal_1.id,
        })

        self.assertEqual(voucher.amount_total_net, 0.0)

        voucher.write({
            'bank_transfer_ids': [(0, 0, {
                'journal_id': self.bank_journal_1.id,
                'destination_journal_id': self.bank_journal_2.id,
                'amount': 300.0,
                'date': fields.Date.today(),
            })]
        })

        self.assertEqual(voucher.amount_total_net, 300.0)
        self.assertEqual(voucher.amount_total_net_display, 300.0)
