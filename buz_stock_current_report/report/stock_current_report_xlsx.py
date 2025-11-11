from odoo import models
from datetime import datetime
import logging
_logger = logging.getLogger(__name__)

class StockCurrentReportXlsx(models.AbstractModel):
    _name = 'report.buz_stock_current_report.stock_current_report_xlsx'
    _inherit = 'report.report_xlsx.abstract'
    _description = 'Current Stock Report Excel (By Date)'

    def generate_xlsx_report(self, workbook, data, wizard):
        _logger.info("Generating Current Stock Excel Report")
        try:
            sheet = workbook.add_worksheet('Current Stock')
            bold = workbook.add_format({'bold': True})

            headers = ['Location', 'Product', 'Category', 'Qty', 'UoM']
            for col, header in enumerate(headers):
                sheet.write(0, col, header, bold)

            stock_date = data.get('stock_date')
            sheet.write(1, 0, f"Stock as of: {stock_date}", bold)
            _logger.info(f"Generating report for stock date: {stock_date}")

            # get stock by date
            stock_lines = self.env['stock.current.report'].compute_stock_at_date(stock_date)
            _logger.info(f"Found {len(stock_lines)} stock lines for report")

            row = 3
            for rec in stock_lines:
                product = self.env['product.product'].browse(rec['product_id'])
                location = self.env['stock.location'].browse(rec['location_id'])
                uom = self.env['uom.uom'].browse(rec['uom_id'])
                sheet.write(row, 0, location.display_name)
                sheet.write(row, 1, product.display_name)
                sheet.write(row, 2, product.categ_id.display_name)
                sheet.write(row, 3, rec['quantity'])
                sheet.write(row, 4, uom.display_name)
                row += 1
            
            _logger.info("Successfully completed Excel report generation")
        except Exception as e:
            _logger.error(f"Error generating Excel report: {e}")
            raise