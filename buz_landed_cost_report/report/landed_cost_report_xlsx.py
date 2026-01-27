from odoo import models

class LandedCostXlsx(models.AbstractModel):
    _name = 'report.buz_landed_cost_report.xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, wizards):
        domain = data.get('domain', [])
        # Search on Summary Model
        summaries = self.env['buz.landed.cost.report'].search(domain, order='doc_no, product_id, id')

        # SHEET 1: SUMMARY
        sheet_summary = workbook.add_worksheet("Summary")
        bold_bg = workbook.add_format({'bold': True, 'bg_color': '#f0f0f0', 'border': 1})
        bold = workbook.add_format({'bold': True})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        num_fmt = workbook.add_format({'num_format': '#,##0.00'})
        
        headers_summary = [
            'DocNo', 'Date', 'RefNo', 'Product Code', 'Product Name',
            'Qty', 'Price/Unit USD', 'Cost USD (Base)', 'Rate',
            'Total Expense THB', 'Total Cost THB', 'Unit Cost THB', 'Inventory Name'
        ]
        
        for col, h in enumerate(headers_summary):
            sheet_summary.write(0, col, h, bold_bg)

        row_s = 1
        for line in summaries:
            sheet_summary.write(row_s, 0, line.doc_no or '')
            if line.date:
                sheet_summary.write(row_s, 1, line.date, date_format)
            else:
                sheet_summary.write(row_s, 1, '')
            sheet_summary.write(row_s, 2, line.ref_no or '')
            sheet_summary.write(row_s, 3, line.product_id.default_code or '')
            sheet_summary.write(row_s, 4, line.product_id.name or '')
            
            sheet_summary.write(row_s, 5, line.qty, num_fmt)
            sheet_summary.write(row_s, 6, line.price_unit_usd, num_fmt)
            sheet_summary.write(row_s, 7, line.cost_usd, num_fmt)
            sheet_summary.write(row_s, 8, line.rate, num_fmt)
            
            sheet_summary.write(row_s, 9, line.total_expense_thb, num_fmt)
            sheet_summary.write(row_s, 10, line.total_cost_thb, bold) # Bold Total
            sheet_summary.write(row_s, 11, line.unit_cost_thb, bold) # Bold Unit
            sheet_summary.write(row_s, 12, line.inventory_name or '')
            row_s += 1

        # SHEET 2: DETAIL
        sheet_detail = workbook.add_worksheet("Cost Breakdown")
        headers_detail = [
            'DocNo', 'Product',
            'Cost Line', 'Account Code', 'Account Name', 
            'Amount THB', 'Inventory Name'
        ]
        for col, h in enumerate(headers_detail):
            sheet_detail.write(0, col, h, bold_bg)

        row_d = 1
        # To make Sheet 2 useful, we probably want to see *all* details corresponding to the filter.
        # Iterating summaries and then their details ensures we match the filter.
        for summary in summaries:
            for detail in summary.detail_ids:
                sheet_detail.write(row_d, 0, summary.doc_no or '')
                sheet_detail.write(row_d, 1, summary.product_id.display_name or '')
                
                sheet_detail.write(row_d, 2, detail.cost_line_name or '')
                sheet_detail.write(row_d, 3, detail.account_code or '')
                sheet_detail.write(row_d, 4, detail.account_name or '')
                
                sheet_detail.write(row_d, 5, detail.amount_thb, num_fmt)
                sheet_detail.write(row_d, 6, summary.inventory_name or '')
                row_d += 1
