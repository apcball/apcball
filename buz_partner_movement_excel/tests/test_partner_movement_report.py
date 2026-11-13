from odoo.tests import TransactionCase


class TestPartnerMovementReport(TransactionCase):
    def test_as_of_residual_for_receivable_and_payable(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._signed_residual(100.0, 40.0), 60.0)
        self.assertEqual(report._signed_residual(-100.0, 40.0), -60.0)

    def test_as_of_residual_when_fully_settled(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._signed_residual(100.0, 100.0), 0.0)
        self.assertEqual(report._signed_residual(-100.0, 100.0), 0.0)
