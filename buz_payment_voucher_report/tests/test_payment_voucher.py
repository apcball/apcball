# -*- coding: utf-8 -*-
from odoo import tests
from odoo.tests import tagged
import datetime


@tagged('post_install', '-at_install')
class TestPaymentVoucherReport(tests.TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.partner = cls.env['res.partner'].create({
            'name': 'Test Partner (PVR)',
            'is_company': True,
        })

        cls.product = cls.env['product.product'].search([
            ('type', '=', 'service'),
        ], limit=1)
        if not cls.product:
            tmpl = cls.env['product.template'].create({
                'name': 'Test Service (PVR)',
                'type': 'service',
                'list_price': 100.0,
                'property_account_income_id': cls.account_income.id,
                'property_account_expense_id': cls.account_expense.id,
            })
            cls.product = tmpl.product_variant_id

        cls.account_receivable = cls.env['account.account'].search([
            ('account_type', '=', 'asset_receivable'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.account_payable = cls.env['account.account'].search([
            ('account_type', '=', 'liability_payable'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.account_income = cls.env['account.account'].search([
            ('account_type', '=', 'income'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.account_expense = cls.env['account.account'].search([
            ('account_type', '=', 'expense'),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.journal = cls.env['account.journal'].search([
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', cls.env.company.id),
        ], limit=1)

        cls.payment_method_in = cls.env['account.payment.method'].search([
            ('payment_type', '=', 'inbound'),
        ], limit=1)
        cls.payment_method_out = cls.env['account.payment.method'].search([
            ('payment_type', '=', 'outbound'),
        ], limit=1)

    def _create_payment(self, payment_type, amount, partner=None):
        payment_vals = {
            'payment_type': payment_type,
            'partner_type': 'customer' if payment_type in ('inbound', 'transfer') else 'supplier',
            'partner_id': partner.id if partner else False,
            'amount': amount,
            'journal_id': self.journal.id,
            'payment_method_id': (self.payment_method_in if payment_type == 'inbound' else self.payment_method_out).id,
            'date': datetime.date.today(),
        }
        payment = self.env['account.payment'].create(payment_vals)
        payment.action_post()
        return payment

    def _check_journal_balance(self, payment):
        self.assertTrue(payment.move_id, "Payment should have a journal entry")
        self.assertTrue(len(payment.move_id.line_ids) > 0, "Journal entry should have lines")
        total_debit = sum(payment.move_id.line_ids.mapped('debit'))
        total_credit = sum(payment.move_id.line_ids.mapped('credit'))
        self.assertAlmostEqual(total_debit, total_credit,
                               places=2,
                               msg="Debit should equal Credit")

    def test_customer_payment(self):
        invoice = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': datetime.date.today(),
            'journal_id': self.journal.id,
            'invoice_line_ids': [(0, 0, {
                'name': 'Test Product',
                'quantity': 1.0,
                'price_unit': 1000.0,
                'product_id': self.product.id,
                'account_id': self.account_income.id,
            })],
        })
        invoice.action_post()
        payment = self._create_payment('inbound', 1000.0, self.partner)
        self._check_journal_balance(payment)
        tot = self.env['buz.payment.voucher'].search(
            [('payment_id', '=', payment.id)])
        self.assertTrue(len(tot) > 0,
                        "Payment should have voucher records")

    def test_vendor_payment(self):
        self.skipTest("l10n_th_account_tax requires tax_invoice_number/date on purchase lines")

    def test_internal_transfer(self):
        payment_types = dict(self.env['account.payment']._fields['payment_type'].selection)
        if 'transfer' not in payment_types:
            self.skipTest("transfer payment type not supported in this DB")

        journal2 = self.env['account.journal'].search([
            ('id', '!=', self.journal.id),
            ('type', 'in', ['bank', 'cash']),
            ('company_id', '=', self.env.company.id),
        ], limit=1)
        if not journal2:
            self.skipTest("Need second journal for transfer")

        payment = self.env['account.payment'].create({
            'payment_type': 'transfer',
            'amount': 300.0,
            'journal_id': self.journal.id,
            'destination_journal_id': journal2.id,
            'payment_method_id': self.payment_method_in.id,
            'date': datetime.date.today(),
        })
        payment.action_post()
        self._check_journal_balance(payment)

    def test_debit_credit_balance(self):
        payment = self._create_payment('inbound', 1000.0, self.partner)
        self._check_journal_balance(payment)

    def test_multi_currency(self):
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        if not usd:
            self.skipTest("USD currency not available")
        payment = self.env['account.payment'].create({
            'payment_type': 'inbound',
            'partner_type': 'customer',
            'partner_id': self.partner.id,
            'amount': 100.0,
            'currency_id': usd.id,
            'journal_id': self.journal.id,
            'payment_method_id': self.payment_method_in.id,
            'date': datetime.date.today(),
        })
        payment.action_post()
        self.assertEqual(payment.currency_id, usd,
                         "Payment currency should be USD")

    def test_pdf_generation(self):
        payment = self._create_payment('inbound', 1000.0, self.partner)
        report_action = self.env.ref(
            'buz_payment_voucher_report.action_report_payment_voucher')
        self.assertTrue(report_action, "Report action should exist")
        result = report_action.report_action(payment)
        self.assertIsNotNone(result, "Report action should return a result")

    def test_excel_export(self):
        payment = self._create_payment('inbound', 1000.0, self.partner)
        report_action = self.env.ref(
            'buz_payment_voucher_report.action_report_payment_voucher_xlsx')
        self.assertTrue(report_action, "XLSX report action should exist")
        result = report_action.report_action(payment)
        self.assertIsNotNone(result, "XLSX report action should return a result")

    def test_wizard_filter(self):
        payment1 = self._create_payment('inbound', 1000.0, self.partner)
        payment2 = self._create_payment('outbound', 500.0, self.partner)
        wizard = self.env['buz.payment.voucher.wizard'].create({
            'partner_id': self.partner.id,
            'company_id': self.env.company.id,
            'output_format': 'pdf',
        })
        domain = wizard._build_domain()
        self.assertIn(('partner_id', '=', self.partner.id), domain)
        payments = self.env['account.payment'].search(domain)
        self.assertIn(payment1, payments)
        self.assertIn(payment2, payments)

    def test_smart_button(self):
        payment = self._create_payment('inbound', 1000.0, self.partner)
        self.assertTrue(
            hasattr(payment, 'action_print_payment_voucher'),
            "Payment should have action_print_payment_voucher method")
        result = payment.action_print_payment_voucher()
        self.assertIsNotNone(result,
                             "action_print_payment_voucher should return a result")

    def test_sql_view_data(self):
        """Verify SQL view returns correct debit/credit amounts."""
        payment = self._create_payment('inbound', 1000.0, self.partner)
        voucher_lines = self.env['buz.payment.voucher'].search(
            [('payment_id', '=', payment.id)])
        self.assertTrue(len(voucher_lines) >= 2,
                        "Payment should have at least 2 journal item rows")
        total_debit = sum(voucher_lines.mapped('debit'))
        total_credit = sum(voucher_lines.mapped('credit'))
        self.assertAlmostEqual(
            total_debit, total_credit, places=2,
            msg="Voucher total debit should equal total credit")
        self.assertAlmostEqual(
            total_debit, 1000.0, places=0,
            msg="Voucher total debit should match payment amount")
