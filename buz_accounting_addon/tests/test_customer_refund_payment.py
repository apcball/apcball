from odoo import Command, fields
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.exceptions import UserError
from odoo.tests import tagged


@tagged("post_install", "-at_install")
class TestCustomerRefundPayment(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.credit_note = cls.env["account.move"].create({
            "move_type": "out_refund",
            "partner_id": cls.partner_a.id,
            "invoice_date": fields.Date.today(),
            "invoice_line_ids": [
                Command.create({
                    "product_id": cls.product_a.id,
                    "quantity": 1.0,
                    "price_unit": 4990.0,
                    "tax_ids": [Command.clear()],
                }),
            ],
        })
        cls.credit_note.action_post()

        bank_journal = cls.company_data["default_journal_bank"]
        cls.refund_pv = cls.env["buz.customer.refund.pv"].create({
            "name": "TEST-RPV-0001",
            "date": fields.Date.today(),
            "partner_id": cls.partner_a.id,
            "credit_note_id": cls.credit_note.id,
            "refund_amount": 4000.0,
            "destination_journal_id": bank_journal.id,
            "payment_method_line_id": bank_journal.outbound_payment_method_line_ids[:1].id,
            "state": "posted",
        })

    def _create_refund_wizard(self):
        action = self.refund_pv.action_register_refund_payment()
        return (
            action,
            self.env["account.payment.register"]
            .with_context(**action["context"])
            .create({"cheque_amount": self.refund_pv.refund_amount}),
        )

    def test_refund_action_forces_approved_amount(self):
        action, wizard = self._create_refund_wizard()

        self.assertFalse(action["context"]["batch"])
        self.assertEqual(
            action["context"]["buz_customer_refund_pv_id"],
            self.refund_pv.id,
        )
        self.assertEqual(wizard.amount, 4000.0)

    def test_standard_credit_note_action_remains_unchanged(self):
        action = self.credit_note.action_register_payment()
        self.assertNotIn("buz_customer_refund_pv_id", action["context"])

        wizard = (
            self.env["account.payment.register"]
            .with_context(**action["context"])
            .create({"cheque_amount": self.credit_note.amount_residual})
        )
        self.assertEqual(wizard.amount, 4990.0)

    def test_refund_payment_is_partial_linked_and_reconciled(self):
        _action, wizard = self._create_refund_wizard()
        wizard.make_payments()

        payment = self.refund_pv.payment_ids.filtered(
            lambda record: record.state != "cancel"
        )
        self.assertEqual(len(payment), 1)
        self.assertEqual(payment.amount, 4000.0)
        self.assertEqual(payment.buz_customer_refund_pv_id, self.refund_pv)

        self.credit_note.invalidate_recordset(["amount_residual"])
        self.assertEqual(self.credit_note.amount_residual, 990.0)

    def test_server_rejects_tampered_amount(self):
        _action, wizard = self._create_refund_wizard()
        wizard.amount = 4990.0

        with self.assertRaises(UserError):
            wizard._create_payments()