from odoo.tests import TransactionCase


class TestPartnerMovementReport(TransactionCase):
    def test_period_label_marks_pre_range_documents_as_opening(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._period_label('2026-03-31', '2026-04-01'), 'Opening balance')
        self.assertEqual(report._period_label('2026-04-01', '2026-04-01'), 'Period activity')

    def test_target_move_state_selection(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._move_states('posted'), ['posted'])
        self.assertEqual(report._move_states('all'), ['draft', 'posted'])

    def test_direction_account_types(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._account_types('receivable'), ['asset_receivable'])
        self.assertEqual(report._account_types('payable'), ['liability_payable', 'liability_current'])
        self.assertEqual(report._account_types('both'), [
            'asset_receivable', 'liability_payable', 'liability_current',
        ])

    def test_as_of_residual_for_receivable_and_payable(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._signed_residual(100.0, 40.0), 60.0)
        self.assertEqual(report._signed_residual(-100.0, 40.0), -60.0)

    def test_as_of_residual_when_fully_settled(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._signed_residual(100.0, 100.0), 0.0)
        self.assertEqual(report._signed_residual(-100.0, 100.0), 0.0)
