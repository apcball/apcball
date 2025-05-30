# -*- coding: utf-8 -*-

from odoo import models
import time
from datetime import datetime
from odoo.tools import DEFAULT_SERVER_DATETIME_FORMAT


class ManufacturingReportXlsx(models.AbstractModel):
    _name = 'report.buz_manufacturing_report.manufacturing_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Manufacturing Report XLSX'

    def generate_xlsx_report(self, workbook, data, objects):
        for obj in objects:
            report_name = obj.name
            # One sheet by manufacturing order
            sheet = workbook.add_worksheet(report_name[:31])
            bold = workbook.add_format({'bold': True})
            title = workbook.add_format({'bold': True, 'align': 'center', 'bg_color': '#aaaba8', 'border': True})
            header = workbook.add_format({'bold': True, 'bg_color': '#aaaba8', 'align': 'center', 'border': True})
            date_style = workbook.add_format({'num_format': 'dd/mm/yyyy hh:mm:ss'})
            
            # Sheet formatting
            sheet.set_column('A:A', 20)
            sheet.set_column('B:B', 30)
            sheet.set_column('C:C', 15)
            sheet.set_column('D:D', 15)
            sheet.set_column('E:E', 15)
            sheet.set_column('F:F', 15)
            
            # Title
            sheet.merge_range('A1:F1', 'Manufacturing Report - ' + obj.name, title)
            
            # Manufacturing Order Information
            sheet.write('A3', 'Manufacturing Order:', bold)
            sheet.write('B3', obj.production_id.name)
            sheet.write('A4', 'Product:', bold)
            sheet.write('B4', obj.product_id.display_name)
            sheet.write('A5', 'Quantity:', bold)
            sheet.write('B5', obj.product_qty)
            sheet.write('C5', obj.product_uom_id.name)
            sheet.write('A6', 'Planned Start Date:', bold)
            sheet.write('B6', obj.date_planned_start, date_style)
            sheet.write('A7', 'Planned End Date:', bold)
            sheet.write('B7', obj.date_planned_finished, date_style)
            sheet.write('A8', 'Actual Start Date:', bold)
            sheet.write('B8', obj.date_start or '', date_style)
            sheet.write('A9', 'Actual End Date:', bold)
            sheet.write('B9', obj.date_finished or '', date_style)
            sheet.write('A10', 'Status:', bold)
            sheet.write('B10', dict(self.env['mrp.production']._fields['state'].selection).get(obj.state))
            sheet.write('A11', 'Responsible:', bold)
            sheet.write('B11', obj.user_id.name if obj.user_id else '')
            
            # Raw Materials
            row = 13
            sheet.merge_range(f'A{row}:F{row}', 'Raw Materials', header)
            row += 1
            sheet.write(f'A{row}', 'Product', header)
            sheet.write(f'B{row}', 'Description', header)
            sheet.write(f'C{row}', 'Quantity', header)
            sheet.write(f'D{row}', 'UoM', header)
            sheet.write(f'E{row}', 'Available', header)
            sheet.write(f'F{row}', 'Used', header)
            row += 1
            
            for move in obj.move_raw_ids:
                sheet.write(f'A{row}', move.product_id.default_code or '')
                sheet.write(f'B{row}', move.product_id.name)
                sheet.write(f'C{row}', move.product_uom_qty)
                sheet.write(f'D{row}', move.product_uom.name)
                sheet.write(f'E{row}', 0)  # Reserved quantity is no longer available in Odoo 17
                sheet.write(f'F{row}', 0)  # Consumed quantity is no longer available in Odoo 17
                row += 1
            
            # Work Orders
            row += 2
            sheet.merge_range(f'A{row}:F{row}', 'Work Orders', header)
            row += 1
            sheet.write(f'A{row}', 'Operation', header)
            sheet.write(f'B{row}', 'Work Center', header)
            sheet.write(f'C{row}', 'Status', header)
            sheet.write(f'D{row}', 'Start Date', header)
            sheet.write(f'E{row}', 'End Date', header)
            sheet.write(f'F{row}', 'Duration (h)', header)
            row += 1
            
            for workorder in obj.workorder_ids:
                sheet.write(f'A{row}', workorder.name)
                sheet.write(f'B{row}', workorder.workcenter_id.name)
                sheet.write(f'C{row}', dict(self.env['mrp.workorder']._fields['state'].selection).get(workorder.state))
                sheet.write(f'D{row}', workorder.date_start or '', date_style)
                sheet.write(f'E{row}', workorder.date_finished or '', date_style)
                duration = 0
                if workorder.date_start and workorder.date_finished:
                    duration = (workorder.date_finished - workorder.date_start).total_seconds() / 3600
                sheet.write(f'F{row}', round(duration, 2))
                row += 1
            
            # Notes
            if obj.notes:
                row += 2
                sheet.merge_range(f'A{row}:F{row}', 'Notes', header)
                row += 1
                sheet.merge_range(f'A{row}:F{row+2}', obj.notes)
                
            # Report generation info
            row += 5
            sheet.write(f'A{row}', 'Report Date:', bold)
            sheet.write(f'B{row}', obj.report_date, workbook.add_format({'num_format': 'dd/mm/yyyy'}))
            sheet.write(f'E{row}', 'Generated by:', bold)
            sheet.write(f'F{row}', self.env.user.name)