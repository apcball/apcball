import io
import zipfile
from datetime import date

from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestPurchaseOrderMonthlyReport(TransactionCase):

    def test_report_headers_match_reference_order(self):
        report = self.env['buz.po.monthly.report.xlsx.generator']
        self.assertEqual(report.HEADERS, [
            'ลำดับ', 'เลขที่เอกสาร', 'วันที่เปิดPO', 'รหัสผู้จำหน่าย',
            'ชื่อผู้จำหน่าย', 'Ref', 'กำหนดส่ง', 'วันที่ Approve', 'ชื่อ', 'ราคา',
            'จำนวน', 'AMOUNT', 'รับ', 'คงเหลือ', 'สถานที่ส่ง', 'CREDIT',
        ])

    def test_selected_pr_states_returns_only_checked_states(self):
        wizard = self.env['po.monthly.report.wizard'].new({
            'pr_state_waiting_purchase_approval': True,
            'pr_state_approved': True,
        })
        report = self.env['buz.po.monthly.report.xlsx.generator']
        self.assertEqual(
            report._selected_pr_states(wizard),
            ['waiting_purchase_approval', 'approved'],
        )

    def test_no_selected_pr_state_disables_status_filter(self):
        wizard = self.env['po.monthly.report.wizard'].new({})
        report = self.env['buz.po.monthly.report.xlsx.generator']
        self.assertEqual(report._selected_pr_states(wizard), [])

    def test_at_least_one_complete_date_range_is_required(self):
        wizard_model = self.env['po.monthly.report.wizard']
        with self.assertRaises(ValidationError):
            wizard_model.new({})._check_date_ranges()

        wizard = wizard_model.new({
            'po_date_from': date(2026, 5, 1),
            'po_date_to': date(2026, 5, 31),
        })
        wizard._check_date_ranges()

    def test_partial_and_reversed_ranges_are_rejected(self):
        wizard_model = self.env['po.monthly.report.wizard']
        partial = wizard_model.new({'po_date_from': date(2026, 5, 1)})
        with self.assertRaises(ValidationError):
            partial._check_date_ranges()

        reversed_range = wizard_model.new({
            'po_date_from': date(2026, 5, 31),
            'po_date_to': date(2026, 5, 1),
        })
        with self.assertRaises(ValidationError):
            reversed_range._check_date_ranges()


    def test_pr_date_fields_are_not_supported(self):
        wizard = self.env['po.monthly.report.wizard']
        self.assertNotIn('pr_date_from', wizard._fields)
        self.assertNotIn('pr_date_to', wizard._fields)

    def test_export_creates_valid_xlsx_for_empty_result(self):
        wizard = self.env['po.monthly.report.wizard'].new({
            'po_date_from': date(1900, 1, 1),
            'po_date_to': date(1900, 1, 2),
        })
        content = self.env[
            'buz.po.monthly.report.xlsx.generator'
        ].generate_xlsx(wizard)
        self.assertTrue(zipfile.is_zipfile(io.BytesIO(content)))
