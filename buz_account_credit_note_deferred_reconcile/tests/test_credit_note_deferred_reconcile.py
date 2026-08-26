from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCreditNoteDeferredReconcile(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls, chart_template_ref=None):
        super().setUpClass(chart_template_ref=chart_template_ref)
        cls.company_data["company"].buz_deferred_credit_note_reconcile = True
        cls.company_data_2["company"].buz_deferred_credit_note_reconcile = True

    def _reverse(self, move, amount=None):
        wizard = self.env["account.move.reversal"].with_context(
            active_model="account.move", active_ids=move.ids
        ).create({
            "date": move.date,
            "reason": "Test reversal",
            "journal_id": move.journal_id.id,
        })
        action = wizard.refund_moves()
        credit_note = self.env["account.move"].browse(action["res_id"]) if action.get("res_id") \
            else self.env["account.move"].browse(action["domain"][0][2])
        if amount is not None:
            credit_note.invoice_line_ids.write({"price_unit": amount})
        credit_note.action_post()
        return credit_note

    def _ar_line(self, move):
        return move.line_ids.filtered(lambda l: l.account_id.account_type == "asset_receivable")

    def _ap_line(self, move):
        return move.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")

    # ---- Test 1: Full Customer Credit Note ----
    def test_01_full_credit_note_deferred(self):
        invoice = self.init_invoice("out_invoice", amounts=[1000.0], taxes=[], post=True)
        credit_note = self._reverse(invoice)

        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(credit_note.payment_state, "not_paid")

        invoice_receivable = self._ar_line(invoice)
        credit_receivable = self._ar_line(credit_note)

        self.assertFalse(invoice_receivable.reconciled)
        self.assertFalse(credit_receivable.reconciled)
        self.assertFalse(invoice_receivable.matched_debit_ids | invoice_receivable.matched_credit_ids)
        self.assertTrue(credit_note.reversed_entry_id == invoice)

    # ---- Test 2: Partial Credit Note ----
    def test_02_partial_credit_note_deferred(self):
        invoice = self.init_invoice("out_invoice", amounts=[1000.0], taxes=[], post=True)
        credit_note = self._reverse(invoice, amount=200.0)

        self.assertEqual(invoice.amount_residual, 1000.0)
        self.assertEqual(credit_note.amount_residual, 200.0)
        self.assertEqual(invoice.payment_state, "not_paid")
        self.assertEqual(credit_note.payment_state, "not_paid")

        invoice_receivable = self._ar_line(invoice)
        self.assertFalse(invoice_receivable.matched_debit_ids | invoice_receivable.matched_credit_ids)

    # ---- Test 3: Existing Partial Payment preserved ----
    def test_03_existing_partial_payment_preserved(self):
        invoice = self.init_invoice("out_invoice", amounts=[1000.0], taxes=[], post=True)

        payment = self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": invoice.partner_id.id,
            "amount": 400.0,
            "journal_id": self.company_data["default_journal_bank"].id,
        })
        payment.action_post()
        (payment.move_id.line_ids + invoice.line_ids).filtered(
            lambda l: l.account_id.account_type == "asset_receivable" and not l.reconciled
        ).reconcile()

        self.assertEqual(invoice.amount_residual, 600.0)
        existing_matches = self._ar_line(invoice).matched_debit_ids | self._ar_line(invoice).matched_credit_ids
        self.assertTrue(existing_matches)

        credit_note = self._reverse(invoice, amount=200.0)

        self.assertEqual(invoice.amount_residual, 600.0)
        self.assertEqual(credit_note.amount_residual, 200.0)
        remaining_matches = self._ar_line(invoice).matched_debit_ids | self._ar_line(invoice).matched_credit_ids
        self.assertTrue(existing_matches <= remaining_matches)
        self.assertFalse(self._ar_line(credit_note).matched_debit_ids | self._ar_line(credit_note).matched_credit_ids)

    # ---- Test 4: Manual Reconcile ----
    def test_04_manual_reconcile_action(self):
        invoice = self.init_invoice("out_invoice", amounts=[1000.0], taxes=[], post=True)
        credit_note = self._reverse(invoice)

        credit_note.action_reconcile_with_original_invoice()

        self.assertTrue(self._ar_line(invoice).reconciled)
        self.assertTrue(self._ar_line(credit_note).reconciled)
        self.assertEqual(credit_note.payment_state, "paid")
        self.assertIn(invoice.payment_state, ("paid", "reversed"))

    # ---- Test 5: Configuration Disabled -> standard Odoo behavior ----
    def test_05_configuration_disabled_standard_behavior(self):
        self.company_data["company"].buz_deferred_credit_note_reconcile = False
        invoice = self.init_invoice("out_invoice", amounts=[1000.0], taxes=[], post=True)
        credit_note = self._reverse(invoice)

        self.assertTrue(self._ar_line(invoice).reconciled)
        self.assertTrue(self._ar_line(credit_note).reconciled)
        self.assertEqual(credit_note.payment_state, "paid")

    # ---- Test 6: Vendor Refund ----
    def test_06_vendor_refund_deferred(self):
        bill = self.init_invoice("in_invoice", amounts=[1000.0], taxes=[], post=True)
        refund = self._reverse(bill)

        self.assertEqual(bill.payment_state, "not_paid")
        self.assertEqual(refund.payment_state, "not_paid")
        bill_payable = self._ap_line(bill)
        self.assertFalse(bill_payable.reconciled)
        self.assertFalse(bill_payable.matched_debit_ids | bill_payable.matched_credit_ids)

    # ---- Test 7: Multi-company ----
    def test_07_multi_company_independent_settings(self):
        self.company_data["company"].buz_deferred_credit_note_reconcile = True
        self.company_data_2["company"].buz_deferred_credit_note_reconcile = False

        invoice_a = self.init_invoice(
            "out_invoice", amounts=[1000.0], taxes=[], post=True, company=self.company_data["company"],
        )
        self._reverse(invoice_a)
        self.assertFalse(self._ar_line(invoice_a).reconciled)

        invoice_b = self.init_invoice(
            "out_invoice", amounts=[1000.0], taxes=[], post=True, company=self.company_data_2["company"],
        )
        self._reverse(invoice_b)
        self.assertTrue(self._ar_line(invoice_b).reconciled)
