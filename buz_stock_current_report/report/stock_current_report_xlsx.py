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
        _logger.info("Generating Stock Excel Report with filters")
        try:
            sheet = workbook.add_worksheet('Stock Report')

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

            _logger.info(f"Report filters - Date: {date_from} to {date_to}")

            # ── Write header / filter info ──
            sheet.write(0, 0, 'Stock Movement Report', bold)
            row = 1
            sheet.write(row, 0, 'Date From (ยอดยกมา):', bold)
            sheet.write(row, 1, date_from)
            row += 1
            sheet.write(row, 0, 'Date To (คงเหลือ):', bold)
            sheet.write(row, 1, date_to)
            row += 1

            if location_ids:
                locations = self.env['stock.location'].browse(location_ids)
                sheet.write(row, 0, 'Locations:', bold)
                sheet.write(row, 1, ', '.join([loc.display_name for loc in locations]))
            else:
                sheet.write(row, 0, 'Locations:', bold)
                sheet.write(row, 1, 'All internal and transit locations')
            row += 1

            if product_ids:
                products = self.env['product.product'].browse(product_ids)
                sheet.write(row, 0, 'Products:', bold)
                sheet.write(row, 1, ', '.join([p.display_name for p in products]))
            else:
                sheet.write(row, 0, 'Products:', bold)
                sheet.write(row, 1, 'All products')
            row += 1

            if category_ids:
                categories = self.env['product.category'].browse(category_ids)
                sheet.write(row, 0, 'Categories:', bold)
                sheet.write(row, 1, ', '.join([cat.display_name for cat in categories]))
            else:
                sheet.write(row, 0, 'Categories:', bold)
                sheet.write(row, 1, 'All categories')
            row += 2

            # ── Table headers ──
            has_cost_access = self.env.user.has_group('buz_stock_current_report.group_stock_cost_viewer')

            headers = [
                'Location', 'Location Type', 'Internal Ref', 'Product', 'Category',
                'ยอดยกมา (Begin)',  # stock at date_from
                'ขาเข้า (In)',       # incoming during period
                'ขาออก (Out)',      # outgoing during period
                'คงเหลือ (End)',     # stock at date_to
            ]
            if has_cost_access:
                headers.extend(['Unit Cost', 'Total Value'])
            headers.append('UoM')

            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_format)
            row += 1

            # ── Fetch data ──
            stock_lines = self.env['stock.current.export.wizard'].get_filtered_stock_data(
                date_from=date_from,
                date_to=date_to,
                location_ids=location_ids if location_ids else None,
                product_ids=product_ids if product_ids else None,
                category_ids=category_ids if category_ids else None
            )
            _logger.info(f"Found {len(stock_lines)} stock lines for report")

            # ── Write data rows ──
            total_value = 0
            for rec in stock_lines:
                product = self.env['product.product'].browse(rec['product_id'])
                location = self.env['stock.location'].browse(rec['location_id'])
                category = self.env['product.category'].browse(rec['category_id'])
                uom = self.env['uom.uom'].browse(rec['uom_id'])
                loc_type = rec.get('location_type_name') or rec.get('location_usage') or ''

                col = 0
                sheet.write(row, col, location.display_name); col += 1
                sheet.write(row, col, loc_type); col += 1
                sheet.write(row, col, product.default_code or ''); col += 1
                sheet.write(row, col, product.display_name); col += 1
                sheet.write(row, col, category.display_name if category else ''); col += 1
                sheet.write(row, col, rec.get('begin_qty', 0), number_format); col += 1   # ยอดยกมา
                sheet.write(row, col, rec.get('incoming', 0), number_format); col += 1     # ขาเข้า
                sheet.write(row, col, rec.get('outgoing', 0), number_format); col += 1     # ขาออก
                sheet.write(row, col, rec.get('end_qty', 0), number_format); col += 1      # คงเหลือ

                if has_cost_access:
                    sheet.write(row, col, rec.get('unit_cost', 0), number_format); col += 1
                    sheet.write(row, col, rec.get('total_value', 0), number_format); col += 1
                    total_value += rec.get('total_value', 0)

                sheet.write(row, col, uom.display_name if uom else '')
                row += 1

            # ── Summary row (cost) ──
            if has_cost_access:
                row += 1
                col_sum = 10  # Total Value column index
                sheet.write(row, col_sum - 1, 'Total Value:', bold)
                sheet.write(row, col_sum, total_value, number_format)

            # ── Column widths ──
            sheet.set_column('A:A', 25)   # Location
            sheet.set_column('B:B', 16)   # Location Type
            sheet.set_column('C:C', 20)   # Internal Ref
            sheet.set_column('D:D', 30)   # Product
            sheet.set_column('E:E', 20)   # Category
            sheet.set_column('F:F', 16)   # ยอดยกมา
            sheet.set_column('G:G', 14)   # ขาเข้า
            sheet.set_column('H:H', 14)   # ขาออก
            sheet.set_column('I:I', 16)   # คงเหลือ
            if has_cost_access:
                sheet.set_column('J:J', 14)   # Unit Cost
                sheet.set_column('K:K', 16)   # Total Value
                sheet.set_column('L:L', 12)   # UoM
            else:
                sheet.set_column('J:J', 12)   # UoM

            _logger.info("Successfully completed Excel report generation")
        except Exception as e:
            _logger.error(f"Error generating Excel report: {e}")
            raise
