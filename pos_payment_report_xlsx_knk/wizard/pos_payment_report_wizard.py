# -*- coding: utf-8 -*-
# Powered by Kanak Infosystems LLP.
# © 2020 Kanak Infosystems LLP. (<https://www.kanakinfosystems.com>).

import base64
import io
import xlsxwriter

from odoo import _, fields, models
from odoo.exceptions import UserError


class PosPaymentReportWizard(models.TransientModel):
    _name = 'pos.payment.report.wizard'
    _description = 'POS Payment Report Wizard'

    date_start = fields.Date(string="Start Date", default=fields.Date.context_today)
    date_end = fields.Date(string="End Date", default=fields.Date.context_today)
    payment_method_ids = fields.Many2many('pos.payment.method', string="Payment Methods")
    generated_xlsx_file = fields.Binary(string="Generated XLSX Report")

    def action_generate_xlsx_report(self):
        domain = [('state', 'not in', ['draft', 'cancel'])]
        if self.date_start:
            domain += [('date_order', '>=', self.date_start)]
        if self.date_end:
            domain += [('date_order', '<=', self.date_end)]

        pos_orders = self.env['pos.order'].sudo().search(domain, order='date_order DESC')

        if not pos_orders:
            raise UserError(_("No order records were found for the specified date range."))

        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output)
        worksheet = workbook.add_worksheet('Orders')

        bold = workbook.add_format({'bold': True})
        date_format = workbook.add_format({'num_format': 'yyyy-mm-dd'})

        headers = ['Order', 'Customer', 'Date', 'Session', 'Cashier', 'Receipt Number', 'Currency', 'Order Total', 'Payment Method', 'Payment Amount']
        for col, header in enumerate(headers):
            worksheet.write(0, col, header, bold)

        row = 1
        for order in pos_orders:
            payment_methods = order.payment_ids
            if self.payment_method_ids:
                payment_methods = payment_methods.filtered(lambda p: p.payment_method_id in self.payment_method_ids)
            for payment in payment_methods:
                worksheet.write(row, 0, order.name or "")
                worksheet.write(row, 1, order.partner_id.name if order.partner_id else "")
                worksheet.write(row, 2, order.date_order.strftime('%Y-%m-%d') if order.date_order else "", date_format)
                worksheet.write(row, 3, order.session_id.display_name)
                worksheet.write(row, 4, order.user_id.name if order.user_id else "")
                worksheet.write(row, 5, order.pos_reference or "")
                worksheet.write(row, 6, order.currency_id.name if order.currency_id else "")
                worksheet.write(row, 7, order.amount_total)
                worksheet.write(row, 8, payment.payment_method_id.name)
                worksheet.write(row, 9, payment.amount)
                row += 1

        if row == 1:
            raise UserError(_("No order records were found for the specified date range."))

        workbook.close()
        output.seek(0)

        self.generated_xlsx_file = base64.b64encode(output.getvalue())

        return {
            "type": "ir.actions.act_url",
            "target": "self",
            "url": "/web/content?model=pos.payment.report.wizard"
                   "&field=generated_xlsx_file"
                   "&download=true"
                   "&filename={filename}"
                   "&id={record_id}".format(
                       filename=f'POS Payment Report {fields.Date.today().strftime("%d-%b-%Y")}.xlsx',
                       record_id=self.id
                   ),
        }
