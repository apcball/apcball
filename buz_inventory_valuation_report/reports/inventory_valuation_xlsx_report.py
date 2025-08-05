# -*- coding: utf-8 -*-

from odoo import models, http
from odoo.http import request
import io
import base64
from datetime import datetime
import json


class InventoryValuationXlsxReport(models.AbstractModel):
    _name = 'report.buz_inventory_valuation_report.xlsx_template'
    _description = 'Inventory Valuation XLSX Report'

    def _generate_csv_content(self, data):
        """Generate CSV content as alternative to XLSX"""
        output = io.StringIO()
        
        # Write header information
        output.write("Current Inventory Valuation Report\n")
        output.write(f"Company: {data.get('company', {}).name if data.get('company') else ''}\n")
        output.write(f"Report Period: {data.get('start_date', '')} to {data.get('end_date', '')} (Reference)\n")
        output.write("\n")
        
        # Write column headers
        headers = [
            'Product Code',
            'Product Name', 
            'Category',
            'Location',
            'Quantity',
            'UoM',
            'Unit Cost',
            'Total Value'
        ]
        output.write(','.join(headers) + '\n')
        
        # Write data rows
        inventory_data = data.get('inventory_data', [])
        for item in inventory_data:
            row = [
                str(item.get('product_code', '')),
                str(item.get('product_name', '')).replace(',', ';'),
                str(item.get('category', '')).replace(',', ';'),
                str(item.get('location', '')).replace(',', ';'),
                str(item.get('quantity', 0)),
                str(item.get('uom', '')),
                str(item.get('unit_cost', 0)),
                str(item.get('total_value', 0))
            ]
            output.write(','.join(row) + '\n')
        
        # Write total
        if inventory_data:
            output.write(f"Total Value:,,,,,,,{data.get('total_value', 0)}\n")
        
        # Write generation timestamp
        output.write(f"\nGenerated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        
        content = output.getvalue()
        output.close()
        return content

    def _create_xlsx_report(self, data):
        """Create XLSX report content"""
        try:
            import xlsxwriter
            
            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {'in_memory': True})
            
            # Create worksheet
            sheet = workbook.add_worksheet('Inventory Valuation Report')
            
            # Define formats
            title_format = workbook.add_format({
                'bold': True,
                'font_size': 16,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#E6E6FA'
            })
            
            header_format = workbook.add_format({
                'bold': True,
                'font_size': 12,
                'align': 'center',
                'valign': 'vcenter',
                'bg_color': '#D3D3D3',
                'border': 1
            })
            
            cell_format = workbook.add_format({
                'font_size': 10,
                'align': 'left',
                'valign': 'vcenter',
                'border': 1
            })
            
            number_format = workbook.add_format({
                'font_size': 10,
                'align': 'right',
                'valign': 'vcenter',
                'border': 1,
                'num_format': '#,##0.00'
            })

            # Set column widths
            sheet.set_column('A:A', 15)  # Product Code
            sheet.set_column('B:B', 30)  # Product Name
            sheet.set_column('C:C', 20)  # Category
            sheet.set_column('D:D', 25)  # Location
            sheet.set_column('E:E', 12)  # Quantity
            sheet.set_column('F:F', 10)  # UoM
            sheet.set_column('G:G', 15)  # Unit Cost
            sheet.set_column('H:H', 18)  # Total Value

            # Write title
            sheet.merge_range('A1:H1', 'Current Inventory Valuation Report', title_format)
            
            # Write company and date info
            row = 2
            sheet.write(row, 0, 'Company:', header_format)
            sheet.write(row, 1, data.get('company', {}).name if data.get('company') else '', cell_format)
            
            row += 1
            sheet.write(row, 0, 'Report Period:', header_format)
            date_range = f"{data.get('start_date', '')} to {data.get('end_date', '')} (Reference)"
            sheet.write(row, 1, date_range, cell_format)

            # Write table headers
            row += 3
            headers = [
                'Product Code', 'Product Name', 'Category', 'Location',
                'Quantity', 'UoM', 'Unit Cost', 'Total Value'
            ]
            
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_format)

            # Write data rows
            row += 1
            inventory_data = data.get('inventory_data', [])
            
            for item in inventory_data:
                sheet.write(row, 0, item.get('product_code', ''), cell_format)
                sheet.write(row, 1, item.get('product_name', ''), cell_format)
                sheet.write(row, 2, item.get('category', ''), cell_format)
                sheet.write(row, 3, item.get('location', ''), cell_format)
                sheet.write(row, 4, item.get('quantity', 0), number_format)
                sheet.write(row, 5, item.get('uom', ''), cell_format)
                sheet.write(row, 6, item.get('unit_cost', 0), number_format)
                sheet.write(row, 7, item.get('total_value', 0), number_format)
                row += 1

            # Write total
            if inventory_data:
                row += 1
                sheet.write(row, 6, 'Total Value:', header_format)
                sheet.write(row, 7, data.get('total_value', 0), number_format)
            
            workbook.close()
            output.seek(0)
            return output.getvalue()
            
        except ImportError:
            # Fallback to CSV if xlsxwriter is not available
            return self._generate_csv_content(data).encode('utf-8')


class InventoryValuationXlsxController(http.Controller):
    
    @http.route('/report/xlsx/inventory_valuation', type='http', auth='user')
    def download_xlsx_report(self, **kwargs):
        """Download XLSX report"""
        data = json.loads(kwargs.get('data', '{}'))
        
        report_model = request.env['report.buz_inventory_valuation_report.xlsx_template']
        content = report_model._create_xlsx_report(data)
        
        filename = f"inventory_valuation_{data.get('start_date', '')}_to_{data.get('end_date', '')}.xlsx"
        
        return request.make_response(
            content,
            headers=[
                ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
                ('Content-Disposition', f'attachment; filename="{filename}"')
            ]
        )
