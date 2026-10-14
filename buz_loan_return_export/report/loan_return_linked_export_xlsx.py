# -*- coding: utf-8 -*-

from datetime import datetime, time

from odoo import models


class LoanReturnLinkedExportXlsx(models.AbstractModel):
    _name = 'report.buz_loan_return_export.loan_return_linked_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Directly Linked BG/RBG XLSX Report'

    def generate_xlsx_report(self, workbook, data, wizards):
        wizard = wizards[:1]
        rows = wizard._get_report_rows()
        sheet = workbook.add_worksheet('Linked BG RBG')
        sheet.freeze_panes(1, 0)
        headers = [
            'BG Number', 'BG Completed Date', 'RBG Documents', 'Contact',
            'Product Code', 'Product', 'Unit', 'Loaned', 'Returned', 'Balance', 'Warning',
        ]
        widths = [22, 18, 36, 32, 18, 42, 14, 14, 14, 14, 58]
        header_format = workbook.add_format({
            'bold': True, 'align': 'center', 'valign': 'vcenter',
            'text_wrap': True, 'bg_color': '#D9EAF7', 'border': 1,
        })
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        number_format = workbook.add_format({'num_format': '#,##0.###'})
        warning_format = workbook.add_format({'bg_color': '#FFF2CC', 'font_color': '#9C6500'})
        sheet.set_row(0, 30)
        for col, width in enumerate(widths):
            sheet.set_column(col, col, width)
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)
        for row_no, row in enumerate(rows, start=1):
            values = [
                row['bg'], row['bg_date'], row['rbg'], row['partner'],
                row['product_code'], row['product'], row['uom'], row['loaned'],
                row['returned'], row['balance'], row['warning'],
            ]
            for col, value in enumerate(values):
                if col == 1 and value:
                    sheet.write_datetime(row_no, col, datetime.combine(value.date(), time.min), date_format)
                elif col in (7, 8, 9):
                    sheet.write_number(row_no, col, value or 0.0, number_format)
                elif col == 10 and value:
                    sheet.write(row_no, col, value, warning_format)
                else:
                    sheet.write(row_no, col, value or '')
        sheet.autofilter(0, 0, len(rows), len(headers) - 1)