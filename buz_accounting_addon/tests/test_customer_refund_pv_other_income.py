from unittest.mock import MagicMock

from odoo.tests.common import TransactionCase

from ..models.customer_refund_pv import BuzCustomerRefundPv


class TestCustomerRefundPvOtherIncome(TransactionCase):
    def test_register_payment_uses_standard_writeoff_context(self):
        pv = MagicMock()
        pv.env.context = {}
        pv.state = "posted"
        pv.name = "CV/2026/0001"
        pv.refund_amount = 860.0
        pv.payment_ids.filtered.return_value = self.env["account.payment"]
        pv.credit_note_id.move_type = "out_refund"
        pv.credit_note_id.state = "posted"
        pv.credit_note_id.amount_residual_signed = 1000.0
        pv.credit_note_id.with_context.return_value = pv.credit_note_id
        pv.credit_note_id.action_register_payment.return_value = {"context": {}}
        pv.other_income_account_id.id = 123
        pv.destination_journal_id = False
        pv.date = False
        pv.payment_method_line_id = False

        BuzCustomerRefundPv.action_register_refund_payment(pv)

        action_context = pv.credit_note_id.action_register_payment.return_value["context"]
        self.assertEqual(action_context["default_payment_difference_handling"], "reconcile")
        self.assertEqual(action_context["default_writeoff_account_id"], 123)
        self.assertEqual(action_context["default_writeoff_label"], "Other Income - CV/2026/0001")

    def test_account_payment_does_not_override_move_line_preparation(self):
        payment_model = self.env["account.payment"].__class__
        self.assertFalse(
            "_prepare_move_line_default_vals" in payment_model.__dict__,
            "Refund PV must rely on Odoo's standard write-off line preparation.",
        )
