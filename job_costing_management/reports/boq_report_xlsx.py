# -*- coding: utf-8 -*-

from odoo import models
import time
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class BOQReportXlsx(models.AbstractModel):
    _name = 'report.job_costing_management.report_boq_excel'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'BOQ Report XLSX'

    def generate_xlsx_report(self, workbook, data, objects):
        for obj in objects:
            report_name = obj.name
            
            # One sheet by BOQ
            sheet = workbook.add_worksheet(report_name[:31])
            bold = workbook.add_format({'bold': True})
            title = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#aaaba8', 'border': True, 'font_size': 14})
            header = workbook.add_format({'bold': True, 'bg_color': '#aaaba8', 'align': 'center', 'border': True})
            date_style = workbook.add_format({'num_format': 'dd/mm/yyyy'})
            currency_style = workbook.add_format({'num_format': '#,##0.00'})
            currency_bold = workbook.add_format({'num_format': '#,##0.00', 'bold': True})
            cell_border = workbook.add_format({'border': True})
            cell_border_center = workbook.add_format({'border': True, 'align': 'center'})
            cell_border_right = workbook.add_format({'border': True, 'align': 'right'})
            cell_border_right_currency = workbook.add_format({'border': True, 'align': 'right', 'num_format': '#,##0.00'})
            
            # Sheet formatting
            sheet.set_column('A:A', 5)   # No.
            sheet.set_column('B:B', 15)  # Item Code
            sheet.set_column('C:C', 40)  # Description
            sheet.set_column('D:D', 30)  # Specification
            sheet.set_column('E:E', 12)  # Qty
            sheet.set_column('F:F', 10)  # Unit
            sheet.set_column('G:G', 15)  # Unit Cost
            sheet.set_column('H:H', 15)  # Total Cost
            sheet.set_column('I:I', 10)  # Waste %
            sheet.set_column('J:J', 12)  # Adj Qty
            sheet.set_column('K:K', 15)  # Adj Total
            sheet.set_column('L:L', 20)  # Notes
            
            # Title
            sheet.merge_range('A1:L2', 'ใบถอดแบบวัสดุ (BOQ) / BILL OF QUANTITIES', title)
            
            # BOQ Information
            sheet.write('A4', 'บริษัท (Company):', bold)
            sheet.merge_range('B4:D4', obj.company_id.name)
            sheet.write('A5', 'หัวข้อเรื่อง (Title):', bold)
            sheet.merge_range('B5:D5', obj.title)
            sheet.write('A6', 'รายละเอียด (Description):', bold)
            sheet.merge_range('B6:D6', obj.description or '-')
            sheet.write('A7', 'โครงการ (Project):', bold)
            sheet.merge_range('B7:D7', obj.project_id.name if obj.project_id else '')
            
            sheet.write('I4', 'เลขที่เอกสาร:', bold)
            sheet.merge_range('J4:L4', obj.name)
            sheet.write('I5', 'วัน/เดือน/ปี:', bold)
            sheet.merge_range('J5:L5', obj.boq_date.strftime('%d/%m/%Y') if obj.boq_date else '')
            sheet.write('I6', 'Revision:', bold)
            sheet.merge_range('J6:L6', obj.revision or '1.0')
            sheet.write('I7', 'Job Order:', bold)
            sheet.merge_range('J7:L7', obj.job_order_id.name if obj.job_order_id else '')
            
            # Table Header
            row = 9
            sheet.write(row, 0, 'ลำดับ (No.)', header)
            sheet.write(row, 1, 'รหัสสินค้า (Item Code)', header)
            sheet.write(row, 2, 'รายการ (Description)', header)
            sheet.write(row, 3, 'สเปค (Specification)', header)
            sheet.write(row, 4, 'จำนวน (Quantity)', header)
            sheet.write(row, 5, 'หน่วย (Unit)', header)
            sheet.write(row, 6, 'ราคา/หน่วย (Unit Cost)', header)
            sheet.write(row, 7, 'จำนวนเงิน (Total Cost)', header)
            sheet.write(row, 8, 'Waste %', header)
            sheet.write(row, 9, 'Adj. Qty', header)
            sheet.write(row, 10, 'Adj. Total', header)
            sheet.write(row, 11, 'หมายเหตุ (Notes)', header)
            
            # Table lines
            row += 1
            line_index = 1
            current_category = None
            
            for line in obj.line_ids:
                if line.category_id and line.category_id != current_category:
                    # Category row
                    category_name = line.category_id.name
                    if line.category_id.description:
                        category_name += f" - {line.category_id.description}"
                    sheet.merge_range(row, 0, row, 11, category_name, workbook.add_format({'bold': True, 'bg_color': '#e9ecef', 'border': True}))
                    current_category = line.category_id
                    row += 1
                
                sheet.write(row, 0, line_index, cell_border_center)
                sheet.write(row, 1, line.item_code or '', cell_border)
                sheet.write(row, 2, line.description or '', cell_border)
                sheet.write(row, 3, line.specification or '', cell_border)
                sheet.write(row, 4, line.quantity, cell_border_right)
                sheet.write(row, 5, line.uom_id.name if line.uom_id else '', cell_border_center)
                sheet.write(row, 6, line.unit_cost, cell_border_right_currency)
                sheet.write(row, 7, line.total_cost, cell_border_right_currency)
                sheet.write(row, 8, line.waste_percentage, cell_border_center)
                sheet.write(row, 9, line.adjusted_quantity, cell_border_right)
                sheet.write(row, 10, line.adjusted_total_cost, cell_border_right_currency)
                sheet.write(row, 11, line.notes or '', cell_border)
                
                line_index += 1
                row += 1
                
            # Totals
            summary_format = workbook.add_format({'bold': True, 'border': True, 'align': 'right', 'bg_color': '#f8f9fa'})
            sheet.merge_range(row, 0, row, 3, 'รวมจำนวน (Total Quantity):', summary_format)
            sheet.write(row, 4, obj.total_quantity, workbook.add_format({'bold': True, 'border': True, 'align': 'right', 'bg_color': '#f8f9fa'}))
            
            sheet.merge_range(row, 5, row, 6, 'รวมจำนวนเงิน (Total Cost):', summary_format)
            sheet.write(row, 7, obj.total_cost, workbook.add_format({'num_format': '#,##0.00', 'bold': True, 'border': True, 'align': 'right', 'bg_color': '#f8f9fa'}))
            
            # Fill empty adjacent columns
            sheet.write(row, 8, '', summary_format)
            sheet.write(row, 9, '', summary_format)
            sheet.write(row, 10, '', summary_format)
            sheet.write(row, 11, '', summary_format)
            
            # Signatures
            row += 3
            sig_title = workbook.add_format({'align': 'center', 'bold': True})
            sig_line = workbook.add_format({'align': 'center'})
            
            sheet.merge_range(row, 1, row, 3, 'ผู้จัดทำ (Prepared By)', sig_title)
            sheet.merge_range(row, 5, row, 7, 'ผู้ตรวจสอบ (Checked By)', sig_title)
            sheet.merge_range(row, 9, row, 11, 'ผู้อนุมัติ (Approved By)', sig_title)
            
            row += 2
            sheet.merge_range(row, 1, row, 3, '____________________', sig_line)
            sheet.merge_range(row, 5, row, 7, '____________________', sig_line)
            sheet.merge_range(row, 9, row, 11, '____________________', sig_line)
            
            row += 1
            prepared_name = f"({obj.prepared_by.name})" if obj.prepared_by else "(____________________)"
            approved_name = f"({obj.approved_by.name})" if obj.approved_by else "(____________________)"
            sheet.merge_range(row, 1, row, 3, prepared_name, sig_line)
            sheet.merge_range(row, 5, row, 7, '(____________________)', sig_line)
            sheet.merge_range(row, 9, row, 11, approved_name, sig_line)
            
            row += 1
            sheet.merge_range(row, 1, row, 3, '(______/______/______)', sig_line)
            sheet.merge_range(row, 5, row, 7, '(______/______/______)', sig_line)
            sheet.merge_range(row, 9, row, 11, '(______/______/______)', sig_line)
