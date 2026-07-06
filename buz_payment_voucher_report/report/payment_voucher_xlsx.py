# -*- coding: utf-8 -*-
"""
Payment Voucher Report XLSX Export

Generates Excel report using xlsxwriter via report_xlsx module.
"""
from odoo import models
from datetime import datetime


class PaymentVoucherXlsx(models.AbstractModel):
    """
    Payment Voucher Report XLSX Export

    Inherits report.report_xlsx.abstract to generate Excel files
    using xlsxwriter.

    Supports multi-payment export with one sheet per payment.
    """
    _name = 'report.buz_payment_voucher_report.report_payment_voucher_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Payment Voucher Report XLSX'

    def generate_xlsx_report(self, workbook, data, payments):
        """
        Generate XLSX report for selected payments.

        Creates one sheet per payment, each containing:
        - Payment header info
        - Journal items table
        - Totals row

        :param workbook: xlsxwriter Workbook object
        :param data: dict with report data (from wizard)
        :param payments: account.payment recordset
        """
        for payment in payments:
            # Sheet name: payment name (max 31 chars for Excel)
            sheet_name = (payment.name or 'Payment')[:31]
            sheet = workbook.add_worksheet(sheet_name)

            # Define formats
            bold = workbook.add_format({'bold': True})
            title = workbook.add_format({
                'bold': True,
                'align': 'center',
                'bg_color': '#4F81BD',
                'font_color': 'white',
                'border': True,
                'font_size': 14,
            })
            header = workbook.add_format({
                'bold': True,
                'bg_color': '#D3E4F8',
                'align': 'center',
                'border': True,
                'text_wrap': True,
            })
            number = workbook.add_format({'num_format': '#,##0.00'})
            currency_format = workbook.add_format({
                'num_format': '[$$-409]#,##0.00',
            })
            date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})

            # Sheet column widths
            sheet.set_column('A:A', 15)   # Payment Number
            sheet.set_column('B:B', 12)   # Payment Date
            sheet.set_column('C:C', 25)   # Partner
            sheet.set_column('D:D', 20)   # Journal
            sheet.set_column('E:E', 15)   # Account Code
            sheet.set_column('F:F', 30)   # Chart of Account
            sheet.set_column('G:G', 20)   # Line Partner
            sheet.set_column('H:H', 30)   # Label
            sheet.set_column('I:I', 12)   # Debit
            sheet.set_column('J:J', 12)   # Credit
            sheet.set_column('K:K', 10)   # Currency
            sheet.set_column('L:L', 15)   # Amount Currency
            sheet.set_column('M:M', 20)   # Reference
            sheet.set_column('N:N', 20)   # Invoice

            # Title row
            row = 0
            sheet.merge_range(f'A{row+1}:N{row+1}',
                            f'Payment Voucher - {payment.name}',
                            title)
            row += 1

            # Payment header info
            row += 1
            sheet.write(f'A{row+1}', 'Payment Number:', bold)
            sheet.write(f'B{row+1}', payment.name)
            sheet.write(f'C{row+1}', 'Payment Date:', bold)
            sheet.write(f'D{row+1}', payment.date or '', date_format)

            row += 1
            sheet.write(f'A{row+1}', 'Partner:', bold)
            sheet.write(f'B{row+1}', payment.partner_id.name if payment.partner_id else '')
            sheet.write(f'C{row+1}', 'Journal:', bold)
            sheet.write(f'D{row+1}', payment.journal_id.name if payment.journal_id else '')

            row += 1
            sheet.write(f'A{row+1}', 'Payment Method:', bold)
            sheet.write(f'B{row+1}', payment.payment_method_id.name if payment.payment_method_id else '')
            sheet.write(f'C{row+1}', 'Currency:', bold)
            sheet.write(f'D{row+1}', payment.currency_id.name if payment.currency_id else '')

            row += 1
            sheet.write(f'A{row+1}', 'Payment Type:', bold)
            type_label = dict(payment._fields['payment_type'].selection).get(payment.payment_type, '')
            sheet.write(f'B{row+1}', type_label)
            sheet.write(f'C{row+1}', 'Reference:', bold)
            sheet.write(f'D{row+1}', payment.ref or '')

            row += 1
            sheet.write(f'A{row+1}', 'Memo:', bold)
            sheet.write(f'B{row+1}', payment.payment_reference or '')
            sheet.write(f'C{row+1}', 'Move Number:', bold)
            sheet.write(f'D{row+1}', payment.move_id.name if payment.move_id else '')

            # Journal items table
            row += 2
            headers = [
                'Account Code', 'Chart of Account', 'Partner', 'Label',
                'Debit', 'Credit', 'Currency', 'Amount Currency',
                'Reference', 'Invoice'
            ]
            for col, hdr_text in enumerate(headers):
                sheet.write(row, col, hdr_text, header)

            row += 1

            # Write journal items (move lines)
            total_debit = 0.0
            total_credit = 0.0
            for line in payment.move_id.line_ids:
                sheet.write(f'A{row+1}', line.account_id.code or '')
                sheet.write(f'B{row+1}', line.account_id.name or '')
                sheet.write(f'C{row+1}', line.partner_id.name if line.partner_id else '')
                sheet.write(f'D{row+1}', line.name or '')
                sheet.write(f'E{row+1}', line.debit, number)
                sheet.write(f'F{row+1}', line.credit, number)
                sheet.write(f'G{row+1}', payment.currency_id.name or '')
                sheet.write(f'H{row+1}', line.amount_currency or 0.0, number)
                sheet.write(f'I{row+1}', payment.ref or '')
                # Get reconciled invoice for this line
                inv_name = ''
                for matched in line.matched_debit_ids:
                    inv_name = matched.credit_move_id.move_id.name or ''
                for matched in line.matched_credit_ids:
                    inv_name = matched.debit_move_id.move_id.name or ''
                sheet.write(f'J{row+1}', inv_name)

                total_debit += line.debit
                total_credit += line.credit
                row += 1

            # Totals row
            row += 1
            sheet.write(f'D{row+1}', 'Totals:', bold)
            sheet.write(f'E{row+1}', total_debit, number)
            sheet.write(f'F{row+1}', total_credit, number)

            # Difference
            row += 1
            difference = total_debit - total_credit
            sheet.write(f'D{row+1}', 'Difference:', bold)
            sheet.write(f'E{row+1}', difference, number)

            # Reconciled invoices section
            reconciled = payment._get_reconciled_invoices()
            if reconciled:
                row += 3
                sheet.write(f'A{row+1}', 'Reconciled Documents', bold)
                row += 1
                sheet.write(f'A{row+1}', 'Invoice Number', header)
                sheet.write(f'B{row+1}', 'Invoice Date', header)
                sheet.write(f'C{row+1}', 'Partner', header)
                sheet.write(f'D{row+1}', 'Total Amount', header)
                sheet.write(f'E{row+1}', 'Residual', header)
                sheet.write(f'F{row+1}', 'Paid Amount', header)
                row += 1

                for inv in reconciled:
                    sheet.write(f'A{row+1}', inv.name or '')
                    sheet.write(f'B{row+1}', inv.invoice_date or '', date_format)
                    sheet.write(f'C{row+1}', inv.partner_id.name or '')
                    sheet.write(f'D{row+1}', inv.amount_total or 0.0, number)
                    sheet.write(f'E{row+1}', inv.amount_residual or 0.0, number)
                    paid = (inv.amount_total or 0.0) - (inv.amount_residual or 0.0)
                    sheet.write(f'F{row+1}', paid, number)
                    row += 1

            # Report generation info
            row += 3
            sheet.write(f'A{row+1}', 'Report Date:', bold)
            sheet.write(f'B{row+1}', datetime.now(), date_format)
            sheet.write(f'D{row+1}', 'Generated by:', bold)
            sheet.write(f'E{row+1}', self.env.user.name)
