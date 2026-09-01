from odoo.tests import TransactionCase, tagged
from odoo.exceptions import UserError, ValidationError


@tagged("post_install", "-at_install")
class TestCustomerRefundVoucher(TransactionCase):
    """Regression tests for CV partial refund and write-off preparation."""

    def _make_cv(self, residual=4990.0, refund=4900.0):
        cv = self.env["buz.customer.refund.voucher"].new({
            "refund_amount": refund,
        })
        cv.cn_residual = residual
        cv._compute_other_income()
        return cv

    def test_other_income_is_residual_less_refund(self):
        cv = self._make_cv()
        self.assertEqual(cv.other_income_dis, 90.0)

    def test_full_refund_has_no_other_income(self):
        cv = self._make_cv(refund=4990.0)
        self.assertEqual(cv.other_income_dis, 0.0)

    def test_zero_refund_is_rejected(self):
        cv = self._make_cv(refund=0.0)
        with self.assertRaises(UserError):
            cv._validate_refund_amount(4990.0)

    def test_refund_above_residual_is_rejected(self):
        cv = self._make_cv(refund=4990.01)
        with self.assertRaises(UserError):
            cv._validate_refund_amount(4990.0)

    def test_cv_number_is_required(self):
        cv_model = self.env["buz.customer.refund.voucher"]
        with self.assertRaises(ValidationError):
            cv_model._validate_cv_number(False)
        with self.assertRaises(ValidationError):
            cv_model._validate_cv_number("   ")

    def test_cv_number_accepts_accounting_number_without_format(self):
        cv_model = self.env["buz.customer.refund.voucher"]
        self.assertTrue(cv_model._validate_cv_number("บัญชี-REF-001"))
