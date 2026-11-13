from types import SimpleNamespace

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

    def test_sibling_invoice_is_not_repeated_under_shared_payment(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertTrue(report._skip_sibling_invoice(2, 'out_invoice'))
        self.assertTrue(report._skip_sibling_invoice(2, 'in_invoice'))
        self.assertFalse(report._skip_sibling_invoice(1, 'out_invoice'))
        self.assertFalse(report._skip_sibling_invoice(2, 'out_refund'))

    def test_allocation_warning_requires_ambiguous_indirect_entry(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._link_warning(1, 'entry', True), '')
        self.assertEqual(report._link_warning(2, 'entry', False), '')
        self.assertEqual(report._link_warning(2, 'out_invoice', True), '')
        self.assertEqual(report._link_warning(2, 'entry', True), 'Bill allocation unclear')

    def test_multiple_remaining_links_make_indirect_entry_allocation_ambiguous(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        source = SimpleNamespace(id=3)
        ancestor = SimpleNamespace(id=1)
        sibling = SimpleNamespace(id=2)
        downstream = SimpleNamespace(id=4)

        def partial(left, right):
            return SimpleNamespace(
                debit_move_id=SimpleNamespace(move_id=left),
                credit_move_id=SimpleNamespace(move_id=right),
            )

        self.assertTrue(report._has_ambiguous_links(
            source, [partial(source, ancestor), partial(source, sibling), partial(source, downstream)],
            {source.id, ancestor.id},
        ))
        self.assertFalse(report._has_ambiguous_links(
            source, [partial(source, ancestor), partial(source, downstream)], {source.id, ancestor.id},
        ))
