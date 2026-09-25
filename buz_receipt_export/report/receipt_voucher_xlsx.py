# -*- coding: utf-8 -*-

from datetime import datetime

from odoo import models


class ReceiptVoucherXlsx(models.AbstractModel):
    """Generate the accounting Receipt Voucher XLSX export."""

    _name = 'report.buz_receipt_export.receipt_voucher_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Receipt Voucher XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizards):
        wizard = wizards[:1]
        rows = wizard._get_report_rows()
        sheet = workbook.add_worksheet('Receipt Voucher')

        title_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'bg_color': '#4F81BD', 'font_color': 'white',
            'border': True, 'font_size': 14,
        })
        label_format = workbook.add_format({'bold': True})
        header_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'text_wrap': True, 'bg_color': '#D9EAF7', 'border': True,
        })
        text_format = workbook.add_format({'border': True})
        date_format = workbook.add_format({'border': True, 'num_format': 'dd/mm/yyyy'})
        number_format = workbook.add_format({
            'border': True, 'num_format': '#,##0.00;[Red]-#,##0.00',
        })
        total_label_format = workbook.add_format({
            'bold': True, 'border': True, 'bg_color': '#E2F0D9',
        })
        total_number_format = workbook.add_format({
            'bold': True, 'border': True, 'bg_color': '#E2F0D9',
            'num_format': '#,##0.00;[Red]-#,##0.00',
        })

        headers = [
            'ลำดับ', 'ลูกค้า', 'เลขที่ใบสำคัญรับ', 'วันที่ใบสำคัญรับ',
            'เลขที่ใบเสร็จรับเงิน', 'วันที่ใบเสร็จรับเงิน',
            'เลขที่ใบกำกับภาษี', 'วันที่ใบกำกับภาษี', 'จำนวนเงิน',
        ]
        for column, width in enumerate([8, 42, 22, 16, 24, 16, 24, 16, 18]):
            sheet.set_column(column, column, width)

        row = 0
        sheet.merge_range(row, 0, row, len(headers) - 1,
                          'Receipt Voucher Report', title_format)
        sheet.set_row(row, 24)
        row += 2

        metadata = [
            ('Company', wizard.company_id.display_name),
            ('Date Type', wizard.date_type_label),
            ('Date From', wizard.date_from),
            ('Date To', wizard.date_to),
            ('Receipt Status', wizard.status_label),
            ('Amount Basis', wizard.amount_basis_label),
        ]
        for label, value in metadata:
            sheet.write(row, 0, label, label_format)
            if hasattr(value, 'year'):
                sheet.write(row, 1, value, date_format)
            else:
                sheet.write(row, 1, value or '', text_format)
            row += 1

        row += 1
        header_row = row
        for column, header in enumerate(headers):
            sheet.write(row, column, header, header_format)
        sheet.set_row(row, 34)
        row += 1

        for sequence, report_row in enumerate(rows, start=1):
            values = [
                sequence, report_row['partner_name'], report_row['voucher_name'],
                report_row['voucher_date'], report_row['receipt_name'],
                report_row['receipt_date'], report_row['invoice_name'],
                report_row['invoice_date'], report_row['amount'],
            ]
            for column, value in enumerate(values):
                if column in (3, 5, 7) and value:
                    sheet.write(row, column, value, date_format)
                elif column == 8:
                    sheet.write_number(row, column, value or 0.0, number_format)
                elif column == 0:
                    sheet.write_number(row, column, value, text_format)
                else:
                    sheet.write(row, column, value or '', text_format)
            row += 1

        sheet.write(row, 0, 'รวมทั้งสิ้น', total_label_format)
        sheet.merge_range(row, 1, row, 7, '', total_label_format)
        sheet.write_number(
            row, 8, sum(report_row['amount'] for report_row in rows),
            total_number_format,
        )
        sheet.freeze_panes(header_row + 1, 0)
        sheet.autofilter(header_row, 0, max(row - 1, header_row), len(headers) - 1)
        sheet.write(row + 2, 0, 'Generated At', label_format)
        sheet.write_datetime(row + 2, 1, datetime.now(), date_format)
