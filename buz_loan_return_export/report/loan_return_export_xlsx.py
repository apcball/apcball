# -*- coding: utf-8 -*-

from datetime import datetime, time

from odoo import models


class LoanReturnExportXlsx(models.AbstractModel):
    """สร้างไฟล์ Excel รายการยืมและคืนสินค้าโชว์"""

    _name = 'report.buz_loan_return_export.loan_return_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Loan and Return XLSX Export'

    _LOAN_HEADERS = [
        'ลำดับ',
        'NO',
        'DATE',
        'รหัสลูกค้า',
        'ชื่อลูกค้า',
        'รหัสสินค้า',
        'ชื่อสินค้า',
        'จำนวนยืม',
        'จำนวนเหลือ',
        'วันครบกำหนด',
        'ที่ส่ง',
        'Destination Location',
    ]
    _RETURN_HEADERS = [
        'ลำดับ',
        'เลขที่',
        'วันที่',
        'รหัสสินค้า',
        'ชื่อสินค้า',
        'จำนวน',
        'รหัสลูกค้า',
        'ชื่อลูกค้า',
        'อ้างอิง',
        'วันที่ อ้างอิง',
        'พนักงานขาย',
        'วันที่ใบรับคืน',
        'สถานะ',
        'วันที่ดำเนินการ',
        'แผนกที่ไปรับสินค้า',
        'หมายเหตุ',
    ]

    def generate_xlsx_report(self, workbook, data, wizards):
        wizard = wizards[:1]
        report_data = wizard._get_report_data()

        header_format = workbook.add_format({
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'text_wrap': True,
            'bg_color': '#D9EAF7',
            'border': 1,
        })
        text_format = workbook.add_format({'valign': 'top'})
        number_format = workbook.add_format({
            'valign': 'top',
            'num_format': '#,##0.##',
        })
        date_format = workbook.add_format({
            'valign': 'top',
            'num_format': 'dd/mm/yyyy',
        })

        self._write_sheet(
            workbook,
            'รายการยืม',
            self._LOAN_HEADERS,
            report_data['loans'],
            header_format,
            text_format,
            number_format,
            date_format,
            numeric_columns={0, 7, 8},
            date_columns={2, 9},
            widths=[10, 22, 14, 18, 36, 20, 48, 14, 14, 16, 58, 40],
        )
        self._write_sheet(
            workbook,
            'รายการคืน',
            self._RETURN_HEADERS,
            report_data['returns'],
            header_format,
            text_format,
            number_format,
            date_format,
            numeric_columns={0, 5},
            date_columns={2, 9, 11, 13},
            widths=[10, 22, 14, 20, 48, 12, 18, 36, 22, 16, 24, 16, 14, 16, 24, 42],
        )

    @staticmethod
    def _write_sheet(
        workbook,
        sheet_name,
        headers,
        rows,
        header_format,
        text_format,
        number_format,
        date_format,
        numeric_columns,
        date_columns,
        widths,
    ):
        sheet = workbook.add_worksheet(sheet_name)
        sheet.freeze_panes(1, 0)
        sheet.set_row(0, 32)
        for column, width in enumerate(widths):
            sheet.set_column(column, column, width)

        for column, header in enumerate(headers):
            sheet.write(0, column, header, header_format)

        for row_index, values in enumerate(rows, start=1):
            for column, value in enumerate(values):
                if value is None or value is False:
                    sheet.write_blank(row_index, column, None, text_format)
                elif column in date_columns and value:
                    sheet.write_datetime(
                        row_index,
                        column,
                        datetime.combine(value, time.min),
                        date_format,
                    )
                elif column in numeric_columns and isinstance(value, (int, float)):
                    sheet.write_number(row_index, column, value, number_format)
                else:
                    sheet.write(row_index, column, str(value), text_format)

        sheet.autofilter(0, 0, len(rows), len(headers) - 1)

