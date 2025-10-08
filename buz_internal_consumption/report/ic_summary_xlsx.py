from odoo import models


class ICRequestXlsx(models.AbstractModel):
    _name = 'report.buz_internal_consumption.ic_summary_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, requests):
        sheet = workbook.add_worksheet('Internal Consumption Summary')
        
        # Add headers
        bold = workbook.add_format({'bold': True})
        money_format = workbook.add_format({'num_format': '#,##0.00'})
        
        sheet.write(0, 0, 'Request Reference', bold)
        sheet.write(0, 1, 'Date', bold)
        sheet.write(0, 2, 'Requester', bold)
        sheet.write(0, 3, 'Department', bold)
        sheet.write(0, 4, 'Product', bold)
        sheet.write(0, 5, 'Quantity', bold)
        sheet.write(0, 6, 'Unit Cost', bold)
        sheet.write(0, 7, 'Total Cost', bold)
        sheet.write(0, 8, 'Analytic Account', bold)
        
        row = 1
        for req in requests:
            for line in req.line_ids:
                sheet.write(row, 0, req.name)
                sheet.write(row, 1, req.date_request.strftime('%Y-%m-%d') if req.date_request else '')
                sheet.write(row, 2, req.requester_id.name)
                sheet.write(row, 3, req.department_id.name if req.department_id else '')
                sheet.write(row, 4, line.product_id.display_name)
                sheet.write(row, 5, line.qty)
                sheet.write(row, 6, line.unit_cost, money_format)
                sheet.write(row, 7, line.subtotal_cost, money_format)
                sheet.write(row, 8, line.analytic_account_id.name if line.analytic_account_id else '')
                row += 1