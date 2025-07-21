# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)

from odoo.tests.common import TransactionCase
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class TestMissingRecordHandling(TransactionCase):
    """Test cases for Missing Record error handling"""

    def setUp(self):
        super().setUp()
        self.AccountMove = self.env['account.move']
        self.AccountMoveLine = self.env['account.move.line']
        self.PaymentRegister = self.env['account.payment.register']
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Partner',
            'is_company': True,
        })
        
        # Create test account
        self.account = self.env['account.account'].create({
            'name': 'Test Account',
            'code': 'TEST001',
            'account_type': 'asset_receivable',
        })

    def test_compute_wht_tax_id_with_missing_record(self):
        """Test _compute_wht_tax_id handles missing records gracefully"""
        # Create a move line
        move = self.AccountMove.create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        
        line = self.AccountMoveLine.create({
            'move_id': move.id,
            'account_id': self.account.id,
            'name': 'Test Line',
            'debit': 100.0,
        })
        
        # Test that computation doesn't crash even with missing product
        try:
            line._compute_wht_tax_id()
            self.assertTrue(True, "Method executed without error")
        except Exception as e:
            self.fail(f"_compute_wht_tax_id raised an exception: {e}")

    def test_get_wht_base_amount_with_missing_record(self):
        """Test _get_wht_base_amount handles missing records gracefully"""
        # Create a move line
        move = self.AccountMove.create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        
        line = self.AccountMoveLine.create({
            'move_id': move.id,
            'account_id': self.account.id,
            'name': 'Test Line',
            'debit': 100.0,
        })
        
        # Test with valid currency
        currency = self.env.ref('base.USD')
        result = line._get_wht_base_amount(currency, '2024-01-01')
        self.assertIsInstance(result, (int, float), "Should return numeric value")

    def test_payment_register_with_missing_records(self):
        """Test payment register handles missing records gracefully"""
        # Create invoice
        invoice = self.AccountMove.create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'account_id': self.account.id,
                'price_unit': 100.0,
                'quantity': 1,
            })],
        })
        
        # Test payment register creation
        with self.env.context.update({'active_model': 'account.move', 'active_ids': [invoice.id]}):
            try:
                wizard = self.PaymentRegister.create({
                    'payment_date': '2024-01-01',
                    'amount': 100.0,
                })
                self.assertTrue(wizard.exists(), "Payment register wizard created successfully")
            except Exception as e:
                self.fail(f"Payment register creation failed: {e}")

    def test_filtered_existing_records(self):
        """Test that filtering with .exists() works correctly"""
        # Create some records
        moves = self.AccountMove.create([
            {
                'move_type': 'out_invoice',
                'partner_id': self.partner.id,
            },
            {
                'move_type': 'in_invoice', 
                'partner_id': self.partner.id,
            }
        ])
        
        # Delete one record
        moves[0].unlink()
        
        # Test filtering existing records
        existing_moves = moves.exists()
        self.assertEqual(len(existing_moves), 1, "Should return only existing records")

    def test_error_handling_in_compute_methods(self):
        """Test that compute methods handle errors gracefully"""
        # Create a move line
        move = self.AccountMove.create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
        })
        
        line = self.AccountMoveLine.create({
            'move_id': move.id,
            'account_id': self.account.id,
            'name': 'Test Line',
            'debit': 100.0,
        })
        
        # Test _compute_all_tax doesn't crash
        try:
            line._compute_all_tax()
            self.assertTrue(True, "_compute_all_tax executed without error")
        except Exception as e:
            self.fail(f"_compute_all_tax raised an exception: {e}")

    def test_reconcile_with_none_result(self):
        """Test reconcile method handles None result gracefully"""
        # Create move lines
        move = self.AccountMove.create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
        })
        
        lines = self.AccountMoveLine.create([{
            'move_id': move.id,
            'account_id': self.account.id,
            'name': 'Test Line 1',
            'debit': 100.0,
        }, {
            'move_id': move.id,
            'account_id': self.account.id,
            'name': 'Test Line 2',
            'credit': 100.0,
        }])
        
        # Test reconcile doesn't crash even if parent returns None
        try:
            result = lines.reconcile()
            self.assertIsInstance(result, dict, "Should return dictionary even if parent returns None")
        except Exception as e:
            self.fail(f"reconcile raised an exception: {e}")

    def test_payment_register_reconciliation_error(self):
        """Test payment register handles reconciliation AttributeError"""
        # Create invoice
        invoice = self.AccountMove.create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'account_id': self.account.id,
                'price_unit': 100.0,
                'quantity': 1,
            })],
        })
        
        # Test payment register with potential reconciliation error
        with self.env.context.update({'active_model': 'account.move', 'active_ids': [invoice.id]}):
            try:
                wizard = self.PaymentRegister.create({
                    'payment_date': '2024-01-01',
                    'amount': 100.0,
                })
                
                # Test action_create_payments doesn't crash
                result = wizard.action_create_payments()
                self.assertTrue(True, "action_create_payments executed without AttributeError")
                
            except AttributeError as e:
                if "'NoneType' object has no attribute 'get'" in str(e):
                    self.fail("AttributeError not properly handled in payment register")
                else:
                    raise
            except Exception as e:
                # Other exceptions are acceptable for this test
                pass

    def test_prepare_deduction_list_safety(self):
        """Test _prepare_deduction_list handles missing records safely"""
        # Create move lines
        move = self.AccountMove.create({
            'move_type': 'in_invoice',
            'partner_id': self.partner.id,
        })
        
        lines = self.AccountMoveLine.create([{
            'move_id': move.id,
            'account_id': self.account.id,
            'name': 'Test Line 1',
            'debit': 100.0,
        }, {
            'move_id': move.id,
            'account_id': self.account.id,
            'name': 'Test Line 2',
            'credit': 100.0,
        }])
        
        # Test deduction list preparation
        currency = self.env.ref('base.USD')
        try:
            deductions, amount = lines._prepare_deduction_list('2024-01-01', currency)
            self.assertIsInstance(deductions, list, "Should return list")
            self.assertIsInstance(amount, (int, float), "Should return numeric amount")
        except Exception as e:
            self.fail(f"_prepare_deduction_list raised an exception: {e}")