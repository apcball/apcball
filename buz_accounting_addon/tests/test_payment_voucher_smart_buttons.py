from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo import fields
from odoo.tests import tagged


@tagged('post_install', '-at_install')
class TestPaymentVoucherSmartButtons(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.vendor = cls.env['res.partner'].create({
            'name': 'Smart Button Test Vendor',
            'supplier_rank': 1,
        })
        cls.voucher = cls.env['account.payment.voucher'].create({
            'name': 'PV-SMART-BUTTON-TEST',
            'partner_id': cls.vendor.id,
        })
        cls.journal = cls.company_data['default_journal_bank']
        cls.payment_method_line = cls.journal.outbound_payment_method_line_ids[:1]

    def _create_payment(self, **values):
        payment_values = {
            'amount': 10.0,
            'date': fields.Date.context_today(self.voucher),
            'journal_id': self.journal.id,
            'payment_method_line_id': self.payment_method_line.id,
            'partner_id': self.vendor.id,
            'partner_type': 'supplier',
            'payment_type': 'outbound',
            'company_id': self.voucher.company_id.id,
        }
        payment_values.update(values)
        return self.env['account.payment'].create(payment_values)

    def test_smart_button_uses_all_payment_links_without_duplicates(self):
        direct = self._create_payment(
            buz_payment_voucher_id=self.voucher.id,
            ref='unrelated reference',
        )
        line = self._create_payment(ref='unrelated reference')
        self.voucher.line_ids = [(0, 0, {
            'payment_ids': [(4, line.id)],
        })]
        legacy = self._create_payment(ref=f'PV {self.voucher.name}')
        duplicate = self._create_payment(
            buz_payment_voucher_id=self.voucher.id,
            ref=f'PV {self.voucher.name}',
        )

        payments = self.voucher._get_smart_button_payments()

        self.assertEqual(set(payments.ids), {direct.id, line.id, legacy.id, duplicate.id})
        self.assertEqual(self.voucher.payment_count, 4)

        action = self.voucher.action_open_related_payments()
        self.assertEqual(set(action['domain'][0][2]), {direct.id, line.id, legacy.id, duplicate.id})
        view_action = self.voucher.action_view_payments()
        self.assertEqual(set(view_action['domain'][0][2]), {direct.id, line.id, legacy.id, duplicate.id})

    def test_smart_button_includes_cancelled_payment(self):
        payment = self._create_payment(ref=f'PV {self.voucher.name}')
        payment.write({'state': 'cancel'})

        self.assertIn(payment, self.voucher._get_smart_button_payments())
        self.assertEqual(self.voucher.payment_count, 1)

    def test_legacy_fallback_excludes_other_vendor(self):
        other_vendor = self.env['res.partner'].create({
            'name': 'Other Smart Button Vendor',
            'supplier_rank': 1,
        })
        other_payment = self._create_payment(
            partner_id=other_vendor.id,
            ref=f'PV {self.voucher.name}',
        )

        self.assertNotIn(other_payment, self.voucher._get_smart_button_payments())
