from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestCustomerRefundVoucher(TransactionCase):
    def _make_cv(self, residual=950.0, refund=900.0):
        cv = self.env["buz.customer.refund.voucher"].new({"refund_amount": refund})
        cv.cn_residual = residual
        cv._compute_other_income()
        return cv

    def test_partial_amount_is_writeoff_difference(self):
        cv = self._make_cv()
        self.assertEqual(cv.other_income_dis, 50.0)
        self.assertEqual(cv.adjustment_method, "writeoff")

    def test_full_refund_has_no_difference(self):
        self.assertEqual(self._make_cv(950.0, 950.0).other_income_dis, 0.0)

    def test_zero_refund_is_rejected(self):
        with self.assertRaises(UserError):
            self._make_cv(refund=0.0)._validate_refund_amount(950.0)

    def test_negative_refund_is_rejected(self):
        with self.assertRaises(UserError):
            self._make_cv(refund=-1.0)._validate_refund_amount(950.0)

    def test_refund_above_residual_is_rejected(self):
        with self.assertRaises(UserError):
            self._make_cv(refund=950.01)._validate_refund_amount(950.0)

    def test_cv_payment_traceability_fields_are_present(self):
        model = self.env["buz.customer.refund.voucher"]
        self.assertIn("partner_bank_id", model._fields)
        self.assertIn("journal_entry_id", model._fields)
        self.assertEqual(model._fields["journal_entry_id"].related, ("payment_id", "move_id"))
    def test_credit_note_cv_action_is_scoped_to_credit_note(self):
        move = self.env["account.move"].new({"move_type": "out_refund"})
        action = move.action_open_buz_cvs()
        self.assertEqual(action["res_model"], "buz.customer.refund.voucher")
        self.assertEqual(action["domain"], [("id", "in", [])])
        self.assertEqual(action["view_mode"], "tree,form")

    def test_cv_number_is_required(self):
        model = self.env["buz.customer.refund.voucher"]
        with self.assertRaises(ValidationError):
            model._validate_cv_number(False)
        with self.assertRaises(ValidationError):
            model._validate_cv_number("   ")

    def test_cv_number_has_no_format_requirement(self):
        model = self.env["buz.customer.refund.voucher"]
        self.assertTrue(model._validate_cv_number("เน€เธยเน€เธยเน€เธเธ’เน€เธเธเน€เธยเน€เธเธ‘เน€เธยเน€เธยเน€เธเธ•-REF-001"))
        self.assertTrue(model._fields["name"].required)
