from odoo import models

class MrpPeriodCostXlsx(models.AbstractModel):
    _name = 'report.buz_mrp_period_cost_allocation.report_xlsx'
    _inherit = 'report.report_xlsx.abstract'

    def generate_xlsx_report(self, workbook, data, docs):
        for o in docs:
            sheet = workbook.add_worksheet(o.name[:31])
            bold = workbook.add_format({'bold': True})
            bold_right = workbook.add_format({'bold': True, 'align': 'right'})
            money = workbook.add_format({'num_format': '#,##0.00'})
            percent = workbook.add_format({'num_format': '0.00%'})
            header_format = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#D3D3D3', 'border': 1})
            text_wrap = workbook.add_format({'text_wrap': True})

            # Header info
            sheet.merge_range('A1:D1', 'Manufacturing Period Cost Allocation', bold)
            sheet.write(1, 0, 'Reference', bold)
            sheet.write(1, 1, o.name)
            sheet.write(2, 0, 'Date From', bold)
            sheet.write(2, 1, str(o.date_from))
            sheet.write(2, 2, 'Date To', bold)
            sheet.write(2, 3, str(o.date_to))
            sheet.write(3, 0, 'Base', bold)
            sheet.write(3, 1, o.allocation_base)
            sheet.write(3, 2, 'Status', bold)
            sheet.write(3, 3, o.state)
            
            if not o.inventory_only:
                sheet.write(4, 0, 'Journal', bold)
                sheet.write(4, 1, o.journal_id.name if o.journal_id else '')
                sheet.write(4, 2, 'Variance Acc', bold)
                sheet.write(4, 3, o.valuation_adjustment_account_id.display_name if o.valuation_adjustment_account_id else '')

            # Section 1: Cost Summary
            row = 6
            sheet.write(row, 0, '1. Cost Summary', bold)
            row += 1
            sheet.write(row, 0, 'Cost Type', header_format)
            sheet.write(row, 1, 'Actual Cost', header_format)
            sheet.write(row, 2, 'Std Cost', header_format)
            sheet.write(row, 3, 'Variance', header_format)
            
            row += 1
            sheet.write(row, 0, 'Direct Labor')
            sheet.write(row, 1, o.actual_dl, money)
            sheet.write(row, 2, o.total_std_dl, money)
            sheet.write(row, 3, o.diff_dl, money)
            
            row += 1
            sheet.write(row, 0, 'Indirect Labor')
            sheet.write(row, 1, o.actual_idl, money)
            sheet.write(row, 2, o.total_std_idl, money)
            sheet.write(row, 3, o.diff_idl, money)
            
            row += 1
            sheet.write(row, 0, 'Overhead')
            sheet.write(row, 1, o.actual_oh, money)
            sheet.write(row, 2, o.total_std_oh, money)
            sheet.write(row, 3, o.diff_oh, money)
            
            row += 1
            sheet.write(row, 0, 'Total', bold)
            sheet.write(row, 1, o.actual_dl + o.actual_idl + o.actual_oh, money)
            sheet.write(row, 2, o.total_std_dl + o.total_std_idl + o.total_std_oh, money)
            sheet.write(row, 3, o.diff_dl + o.diff_idl + o.diff_oh, money)
            
            row += 1
            sheet.write(row, 0, 'Material (Ref)')
            sheet.write(row, 1, '-', money)
            sheet.write(row, 2, o.total_std_material, money)
            sheet.write(row, 3, '-', money)

            # Section 2: Variance Distribution
            row += 2
            sheet.write(row, 0, '2. Variance Distribution', bold)
            row += 1
            sheet.write(row, 0, 'Distribution', header_format)
            sheet.write(row, 1, 'Amount', header_format)
            
            row += 1
            sheet.write(row, 0, 'Allocated to Inventory (Capitalized)')
            sheet.write(row, 1, sum(o.line_ids.mapped('allocated_inventory_total')), money)
            
            row += 1
            sheet.write(row, 0, 'Period Manufacturing Variance (Expense)')
            sheet.write(row, 1, sum(o.line_ids.mapped('allocated_period_expense')), money)
            
            row += 1
            sheet.write(row, 0, 'Total Variance', bold)
            sheet.write(row, 1, o.diff_dl + o.diff_idl + o.diff_oh, money)

            # Section 3: Allocation Details
            row += 3
            sheet.write(row, 0, '3. Allocation Details by MO', bold)
            row += 1
            cols = [
                'MO', 'Product', 'Qty Prod', 'On Hand', 'Ratio %', 'Manual Cost',
                'Alloc DL', 'Alloc IDL', 'Alloc OH', 'Inv Adj', 'Final Inv Cost'
            ]
            for i, col in enumerate(cols):
                sheet.write(row, i, col, header_format)
            
            row += 1
            for line in o.line_ids:
                sheet.write(row, 0, line.mo_id.name)
                sheet.write(row, 1, line.product_id.display_name)
                sheet.write(row, 2, line.quantity_produced)
                sheet.write(row, 3, line.qty_on_hand)
                sheet.write(row, 4, line.inventory_ratio / 100.0, percent)
                sheet.write(row, 5, line.manual_cost, money)
                sheet.write(row, 6, line.allocated_dl, money)
                sheet.write(row, 7, line.allocated_idl, money)
                sheet.write(row, 8, line.allocated_oh, money)
                sheet.write(row, 9, line.allocated_inventory_total, money)
                sheet.write(row, 10, line.standard_total_cost + line.allocated_inventory_total, money)
                row += 1

            # Section 4: Period Variance Breakdown
            row += 2
            sheet.write(row, 0, '4. Period Variance Breakdown (Non-Capitalized)', bold)
            row += 1
            sheet.write(row, 0, 'MO Reference', header_format)
            sheet.write(row, 1, 'Sold / Issued Qty', header_format)
            sheet.write(row, 2, 'Period Variance (Expense)', header_format)
            
            row += 1
            for line in o.line_ids:
                if line.allocated_period_expense != 0:
                     sheet.write(row, 0, line.mo_id.name)
                     sheet.write(row, 1, line.qty_sold)
                     sheet.write(row, 2, line.allocated_period_expense, money)
                     row += 1

            # Section 5: Accounting Note
            row += 2
            sheet.write(row, 0, '5. Accounting & Valuation Note', bold)
            row += 1
            note = "Inventory valuation method: Periodic (No real-time accounting unless enabled).\n" \
                   "This report adjusts inventory valuation only. It does NOT modify historical COGS or repost stock moves.\n" \
                   "Accounting entries are optional and generated only if real-time valuation is enabled."
            sheet.merge_range(row, 0, row + 2, 8, note, text_wrap)

