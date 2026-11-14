from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from xml.etree import ElementTree
from zipfile import ZipFile

import xlsxwriter
from odoo import Command
from odoo.tests import TransactionCase


class TestPartnerMovementReport(TransactionCase):
    def test_reconcile_and_payment_searches_are_batched_across_documents(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        company = self.env.company
        partner = self.env['res.partner'].create({'name': 'Batch Query Partner'})
        journal = self.env['account.journal'].search([
            ('company_id', '=', company.id), ('type', '=', 'sale'),
        ], limit=1)
        income = self.env['account.account'].search([
            ('company_id', '=', company.id), ('account_type', '=', 'income'),
        ], limit=1)
        for index in range(3):
            move = self.env['account.move'].create({
                'move_type': 'out_invoice', 'partner_id': partner.id,
                'journal_id': journal.id, 'invoice_date': '2026-11-10',
                'invoice_line_ids': [Command.create({
                    'name': f'Batch query line {index}', 'quantity': 1,
                    'price_unit': 100.0, 'account_id': income.id,
                    'tax_ids': [Command.clear()],
                })],
            })
            move.action_post()
        wizard = self.env['partner.movement.excel.wizard'].create({
            'date_from': '2026-11-01', 'date_to': '2026-11-14',
            'partner_ids': [Command.set(partner.ids)],
        })

        partial_model = self.env['account.partial.reconcile']
        payment_model = self.env['account.payment']
        partial_search = type(partial_model).search
        payment_search = type(payment_model).search
        calls = {'partial': 0, 'payment': 0}

        def count_partial_search(recordset, *args, **kwargs):
            calls['partial'] += 1
            return partial_search(recordset, *args, **kwargs)

        def count_payment_search(recordset, *args, **kwargs):
            calls['payment'] += 1
            return payment_search(recordset, *args, **kwargs)

        with patch.object(type(partial_model), 'search', count_partial_search), \
                patch.object(type(payment_model), 'search', count_payment_search):
            result = report._report_data(wizard)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['count'], 3)
        self.assertAlmostEqual(result[0]['total'], 300.0)
        self.assertAlmostEqual(result[0]['payment_amount'], 0.0)
        self.assertAlmostEqual(result[0]['residual'], 300.0)
        self.assertLessEqual(calls['partial'], 2)
        self.assertLessEqual(calls['payment'], 1)

    def test_export_places_linked_rows_in_the_same_readable_columns(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        wizard = self.env['partner.movement.excel.wizard'].create({'date_to': '2026-11-14'})
        link = {
            'depth': 1, 'type': 'รายการบัญชี', 'number': 'PAY/001', 'date': '2026-10-01',
            'allocated': 25.0, 'currency': 'THB', 'warning': '', 'journal': 'Bank',
            'target_account': '1010 Bank', 'debit': 0.0, 'credit': 25.0,
            'allocated_currency': 25.0, 'source_currency': 'THB',
        }
        document = {
            'number': 'INV/001', 'type': 'ใบแจ้งหนี้ลูกค้า', 'date': '2026-09-01',
            'journal': 'Sales', 'account': '1100 Receivable', 'debit': 100.0, 'credit': 0.0,
            'currency': 'THB', 'total': 100.0, 'payment_amount': 25.0,
            'adjustment_amount': 0.0, 'residual': 75.0, 'period_label': 'Period activity',
            'state': 'Partial', 'links': [link],
        }
        partner = {
            'partner': SimpleNamespace(display_name='Test Partner'), 'count': 1, 'total': 100.0,
            'payment_amount': 25.0, 'adjustment_amount': 0.0, 'residual': 75.0,
            'docs': [document],
        }
        output = BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        with patch.object(type(report), '_report_data', return_value=[partner]):
            report.generate_xlsx_report(workbook, {}, wizard)
        workbook.close()

        namespace = {'x': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        with ZipFile(output) as xlsx:
            sheets = [name for name in xlsx.namelist() if name.startswith('xl/worksheets/sheet') and name.endswith('.xml')]
            self.assertEqual(len(sheets), 1)
            shared = []
            if 'xl/sharedStrings.xml' in xlsx.namelist():
                shared_root = ElementTree.fromstring(xlsx.read('xl/sharedStrings.xml'))
                shared = [
                    ''.join(node.text or '' for node in item.findall('.//x:t', namespace))
                    for item in shared_root.findall('x:si', namespace)
                ]
            sheet = ElementTree.fromstring(xlsx.read(sheets[0]))
            styles = ElementTree.fromstring(xlsx.read('xl/styles.xml'))

        def cell_value(reference):
            cell = sheet.find(f".//x:c[@r='{reference}']", namespace)
            if cell is None:
                return None
            value = cell.find('x:v', namespace)
            if cell.get('t') == 'inlineStr':
                return ''.join(node.text or '' for node in cell.findall('.//x:t', namespace))
            if cell.get('t') == 's':
                return shared[int(value.text)]
            return value.text if value is not None else None

        def fill_color(style_id):
            xfs = styles.find('x:cellXfs', namespace)
            fills = styles.find('x:fills', namespace)
            fill_id = int(xfs[int(style_id)].get('fillId'))
            color = fills[fill_id].find('x:patternFill/x:fgColor', namespace)
            return color.get('rgb') if color is not None else None

        self.assertEqual(cell_value('A1'), 'คู่ค้า / เลขที่เอกสาร')
        self.assertEqual(cell_value('A2'), 'Test Partner')
        self.assertEqual(cell_value('A3'), 'INV/001')
        self.assertEqual(cell_value('A4'), '  ↳ PAY/001')
        self.assertEqual(cell_value('B3'), 'ใบแจ้งหนี้ลูกค้า')
        self.assertEqual(cell_value('D3'), 'Sales\n1100 Receivable')
        self.assertEqual(cell_value('D4'), 'Bank\n1010 Bank')
        self.assertEqual(cell_value('F4'), '25')
        self.assertEqual(cell_value('L4'), '25')
        partner_row = sheet.find(".//x:row[@r='2']", namespace)
        self.assertEqual(partner_row.get('customFormat'), '1')
        self.assertEqual(fill_color(partner_row.get('s')), 'FFE2F0D9')
        amount_cell = sheet.find(".//x:c[@r='G2']", namespace)
        self.assertEqual(fill_color(amount_cell.get('s')), 'FFE2F0D9')

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

    def test_document_rows_include_every_supported_partner_account_type(self):
        report = self.env['report.buz_partner_movement_excel.partner_movement_xlsx']
        self.assertEqual(report._partner_account_types(), [
            'asset_receivable', 'liability_payable', 'liability_current',
        ])

    def test_export_filename_includes_date_range(self):
        wizard = self.env['partner.movement.excel.wizard']
        self.assertEqual(
            wizard._get_export_filename('2026-09-01', '2026-11-14'),
            'Partner Movement_2026-09-01_to_2026-11-14',
        )
        self.assertEqual(
            wizard._get_export_filename(False, '2026-11-14'),
            'Partner Movement_all_to_2026-11-14',
        )

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
        self.assertEqual(report._link_warning(2, 'entry', True), 'ตรวจสอบการจัดสรร')

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
