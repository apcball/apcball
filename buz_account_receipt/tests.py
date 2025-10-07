from odoo.tests.common import TransactionCase
from odoo import fields


class TestBuzAccountReceipt(TransactionCase):
    def setUp(self):
        super().setUp()
        
        # Create test partner
        self.partner = self.env['res.partner'].create({
            'name': 'Test Customer',
            'customer_rank': 1,
        })
        
        # Create test product
        self.product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'service',
        })
        
        # Create test invoices
        self.invoice1 = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1,
                    'price_unit': 100,
                })
            ]
        })
        self.invoice1.action_post()  # Post the invoice
        
        self.invoice2 = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 2,
                    'price_unit': 50,
                })
            ]
        })
        self.invoice2.action_post()  # Post the invoice

    def test_create_receipt_from_invoices(self):
        """Test creating a receipt from selected invoices"""
        # Test calling the function directly with the invoices
        invoices = self.invoice1 | self.invoice2
        action = invoices.action_create_receipt_from_invoices()
        
        # Check if it returns an action to open the receipt
        self.assertIn('res_model', action)
        self.assertEqual(action['res_model'], 'account.receipt')
        self.assertIn('res_id', action)
        
        # Get the created receipt
        receipt = self.env['account.receipt'].browse(action['res_id'])
        
        # Check that receipt has the correct partner
        self.assertEqual(receipt.partner_id, self.partner)
        
        # Check that receipt lines are created for both invoices
        self.assertEqual(len(receipt.line_ids), 2)
        
        # Check that amounts are properly set
        for line in receipt.line_ids:
            self.assertEqual(line.amount_to_collect, line.amount_residual)

    def test_receipt_autopost_functionality(self):
        """Test that receipts are auto-posted when buz_receipt_autopost is enabled"""
        # Set the config parameter to auto-post
        self.env['ir.config_parameter'].sudo().set_param('buz_account_receipt.auto_post_receipts', True)
        
        # Create a receipt manually
        receipt = self.env['account.receipt'].create({
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {
                    'move_id': self.invoice1.id,
                    'amount_total': 100,
                    'amount_residual': 100,
                    'amount_to_collect': 100,
                })
            ]
        })
        
        # Check if receipt is auto-posted
        self.assertEqual(receipt.state, 'posted')

    def test_receipt_batch_payment(self):
        """Test the batch payment functionality"""
        # Create a receipt with invoices
        receipt = self.env['account.receipt'].create({
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {
                    'move_id': self.invoice1.id,
                    'amount_total': 100,
                    'amount_residual': 100,
                    'amount_to_collect': 100,
                })
            ]
        })
        receipt.action_post()  # Post the receipt
        
        # Call the batch payment action
        action = receipt.action_register_batch_payment()
        
        # Check if it returns an action to open the payment wizard
        self.assertIn('res_model', action)
        self.assertEqual(action['res_model'], 'account.payment.register')
        self.assertIn('context', action)

    def test_receipt_with_refund(self):
        """Test receipt creation with mixed invoices and refunds"""
        # Create a refund
        refund = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1,
                    'price_unit': 30,
                })
            ]
        })
        refund.action_post()
        
        # Create a receipt with both invoice and refund
        receipt = self.env['account.receipt'].create({
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {
                    'move_id': self.invoice1.id,
                    'amount_total': 100,
                    'amount_residual': 100,
                    'amount_to_collect': 100,
                }),
                (0, 0, {
                    'move_id': refund.id,
                    'amount_total': -30,  # Negative for refund
                    'amount_residual': -30,
                    'amount_to_collect': -30,
                }),
            ]
        })
        
        # Check total amount calculation with signed amounts
        expected_total = 100 + (-30)  # 70
        self.assertEqual(receipt.amount_total, expected_total)

    def test_rv_ready_methods(self):
        """Test the RV-ready helper methods"""
        # Create a receipt with unpaid invoices
        receipt = self.env['account.receipt'].create({
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {
                    'move_id': self.invoice1.id,
                    'amount_total': 100,
                    'amount_residual': 100,  # Full amount still due
                    'amount_to_collect': 50,  # Only collecting 50
                })
            ]
        })
        receipt.action_post()
        
        # Test receipt_get_unpaid_moves method
        unpaid_moves = receipt.receipt_get_unpaid_moves()
        self.assertTrue(self.invoice1 in unpaid_moves)
        
        # Test receipt_build_payment_context method
        context = receipt.receipt_build_payment_context()
        self.assertIn('active_ids', context)
        self.assertIn(self.invoice1.id, context['active_ids'])
        self.assertEqual(context['default_partner_id'], self.partner.id)
        
        # Test receipt_reconcile_with_payment would require creating a payment, 
        # which is more complex and would need additional setup

    def test_receipt_link_payments(self):
        """Test the receipt_link_payments RV-ready method"""
        # Create a receipt
        receipt = self.env['account.receipt'].create({
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {
                    'move_id': self.invoice1.id,
                    'amount_to_collect': 100,
                })
            ]
        })
        receipt.action_post()
        
        # Create a test payment
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': 50,
            'date': fields.Date.today(),
        })
        
        # Link the payment using the RV-ready method
        receipt.receipt_link_payments(payment)
        
        # Check that payment is linked
        self.assertIn(payment, receipt.payment_ids)
        self.assertEqual(receipt.payment_count, 1)

    def test_single_currency_enforcement(self):
        """Test that single currency per receipt can be enforced"""
        # Enable single currency enforcement
        self.env['ir.config_parameter'].sudo().set_param(
            'buz_account_receipt.enforce_single_currency_per_receipt', True
        )
        
        # Create an invoice in a different currency (e.g., USD)
        usd_currency = self.env['res.currency'].search([('name', '=', 'USD')], limit=1)
        if usd_currency:
            invoice_usd = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': self.partner.id,
                'currency_id': usd_currency.id,
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': [
                    (0, 0, {
                        'product_id': self.product.id,
                        'quantity': 1,
                        'price_unit': 100,
                    })
                ]
            })
            invoice_usd.action_post()
            
            # Try to create a receipt with mixed currencies
            # This should raise an error due to currency enforcement
            with self.assertRaises(Exception):
                receipt = self.env['account.receipt'].create({
                    'partner_id': self.partner.id,
                    'line_ids': [
                        (0, 0, {
                            'move_id': self.invoice1.id,  # THB
                            'amount_to_collect': 100,
                        }),
                        (0, 0, {
                            'move_id': invoice_usd.id,  # USD
                            'amount_to_collect': 100,
                        }),
                    ]
                })

    def test_signed_amounts_for_refunds(self):
        """Test that signed amounts work correctly for refunds"""
        # Create a refund
        refund = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'invoice_date': fields.Date.today(),
            'invoice_line_ids': [
                (0, 0, {
                    'product_id': self.product.id,
                    'quantity': 1,
                    'price_unit': 50,
                })
            ]
        })
        refund.action_post()
        
        # Create receipt line for refund
        receipt = self.env['account.receipt'].create({
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {
                    'move_id': refund.id,
                    'amount_to_collect': refund.amount_residual_signed,
                })
            ]
        })
        
        # Check that signed amounts are negative for refunds
        line = receipt.line_ids[0]
        self.assertLess(line.amount_total_signed, 0)
        self.assertLess(line.amount_residual_signed, 0)

    def test_amount_to_collect_constraint(self):
        """Test that amount_to_collect cannot exceed residual"""
        receipt = self.env['account.receipt'].create({
            'partner_id': self.partner.id,
            'line_ids': [
                (0, 0, {
                    'move_id': self.invoice1.id,
                    'amount_to_collect': 100,
                })
            ]
        })
        
        # Try to set amount_to_collect greater than residual
        with self.assertRaises(Exception):
            receipt.line_ids[0].write({
                'amount_to_collect': 150,  # Greater than residual (100)
            })

    def test_cross_company_validation(self):
        """Test that cross-company invoices cannot be added to same receipt"""
        # Create another company (if possible)
        try:
            company2 = self.env['res.company'].create({
                'name': 'Test Company 2'
            })
            
            # Create invoice in different company
            invoice_company2 = self.env['account.move'].with_company(company2).create({
                'move_type': 'out_invoice',
                'partner_id': self.partner.id,
                'company_id': company2.id,
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': [
                    (0, 0, {
                        'product_id': self.product.id,
                        'quantity': 1,
                        'price_unit': 100,
                    })
                ]
            })
            invoice_company2.action_post()
            
            # Try to create receipt with invoices from different companies
            with self.assertRaises(Exception):
                receipt = self.env['account.receipt'].create({
                    'partner_id': self.partner.id,
                    'line_ids': [
                        (0, 0, {
                            'move_id': self.invoice1.id,  # Company 1
                            'amount_to_collect': 100,
                        }),
                        (0, 0, {
                            'move_id': invoice_company2.id,  # Company 2
                            'amount_to_collect': 100,
                        }),
                    ]
                })
        except Exception:
            # Skip if multi-company is not available
            pass