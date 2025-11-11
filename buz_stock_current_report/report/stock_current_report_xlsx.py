from odoo import models
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class StockCurrentReportXlsx(models.AbstractModel):
    _name = 'report.buz_stock_current_report.stock_current_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Current Stock Report Excel (By Date with Filters)'

    def generate_xlsx_report(self, workbook, data, wizard):
        """Generate Excel report with filtered stock data"""
        _logger.info("Generating Current Stock Excel Report with filters")
        try:
            sheet = workbook.add_worksheet('Current Stock')
            
            # Define formats
            bold = workbook.add_format({'bold': True})
            header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3'})
            number_format = workbook.add_format({'num_format': '#,##0.00'})
            
            # Get filter data
            date_from = data.get('date_from')
            date_to = data.get('date_to')
            location_ids = data.get('location_ids', [])
            product_ids = data.get('product_ids', [])
            category_ids = data.get('category_ids', [])
            
            _logger.info(f"Report filters - Date: {date_from} to {date_to}, Locations: {location_ids}, Products: {product_ids}, Categories: {category_ids}")
            
            # Write filter information section
            sheet.write(0, 0, 'Stock Report Filters', bold)
            row = 1
            sheet.write(row, 0, 'Date From:', bold)
            sheet.write(row, 1, date_from)
            row += 1
            sheet.write(row, 0, 'Date To:', bold)
            sheet.write(row, 1, date_to)
            row += 1
            
            # Display location filter info
            if location_ids:
                locations = self.env['stock.location'].browse(location_ids)
                sheet.write(row, 0, 'Locations:', bold)
                sheet.write(row, 1, ', '.join([loc.display_name for loc in locations]))
            else:
                sheet.write(row, 0, 'Locations:', bold)
                sheet.write(row, 1, 'All internal locations')
            row += 1
            
            # Display product filter info
            if product_ids:
                products = self.env['product.product'].browse(product_ids)
                sheet.write(row, 0, 'Products:', bold)
                sheet.write(row, 1, ', '.join([p.display_name for p in products]))
            else:
                sheet.write(row, 0, 'Products:', bold)
                sheet.write(row, 1, 'All products')
            row += 1
            
            # Display category filter info
            if category_ids:
                categories = self.env['product.category'].browse(category_ids)
                sheet.write(row, 0, 'Categories:', bold)
                sheet.write(row, 1, ', '.join([cat.display_name for cat in categories]))
            else:
                sheet.write(row, 0, 'Categories:', bold)
                sheet.write(row, 1, 'All categories')
            row += 2
            
            # Write table headers
            headers = ['Location', 'Product', 'Category', 'Qty On Hand', 'Free to Use', 'Incoming', 'Outgoing', 'Unit Cost', 'Total Value', 'UoM']
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_format)
            row += 1
            
            # Fetch filtered stock data
            stock_lines = self.env['stock.current.export.wizard'].get_filtered_stock_data(
                date_from=date_from,
                date_to=date_to,
                location_ids=location_ids if location_ids else None,
                product_ids=product_ids if product_ids else None,
                category_ids=category_ids if category_ids else None
            )
            _logger.info(f"Found {len(stock_lines)} stock lines for report")
            
            # Write data rows
            total_value = 0
            for rec in stock_lines:
                product = self.env['product.product'].browse(rec['product_id'])
                location = self.env['stock.location'].browse(rec['location_id'])
                category = self.env['product.category'].browse(rec['category_id'])
                uom = self.env['uom.uom'].browse(rec['uom_id'])
                
                sheet.write(row, 0, location.display_name)
                sheet.write(row, 1, product.display_name)
                sheet.write(row, 2, category.display_name if category else '')
                sheet.write(row, 3, rec['quantity'], number_format)
                sheet.write(row, 4, rec['free_to_use'], number_format)
                sheet.write(row, 5, rec['incoming'], number_format)
                sheet.write(row, 6, rec['outgoing'], number_format)
                sheet.write(row, 7, rec['unit_cost'], number_format)
                sheet.write(row, 8, rec['total_value'], number_format)
                sheet.write(row, 9, uom.display_name if uom else '')
                
                total_value += rec['total_value']
                row += 1
            
            # Write summary row
            row += 1
            sheet.write(row, 7, 'Total Value:', bold)
            sheet.write(row, 8, total_value, number_format)
            
            # Set column widths
            sheet.set_column('A:A', 25)
            sheet.set_column('B:B', 30)
            sheet.set_column('C:C', 20)
            sheet.set_column('D:H', 15)
            sheet.set_column('I:I', 15)
            sheet.set_column('J:J', 12)
            
            _logger.info("Successfully completed Excel report generation")
        except Exception as e:
            _logger.error(f"Error generating Excel report: {e}")
            raise