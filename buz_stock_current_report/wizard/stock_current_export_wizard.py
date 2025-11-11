from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class StockCurrentExportWizard(models.TransientModel):
    _name = 'stock.current.export.wizard'
    _description = 'Export Current Stock to Excel'

    stock_date = fields.Date(string="Stock Date", required=True, default=fields.Date.context_today)

    def action_export_excel(self):
        _logger.info(f"Exporting stock report for date: {self.stock_date}")
        try:
            report_action = self.env.ref(
                'buz_stock_current_report.action_report_stock_current_xlsx'
            ).report_action(self, data={'stock_date': self.stock_date})
            _logger.info("Successfully generated Excel export action")
            return report_action
        except Exception as e:
            _logger.error(f"Error generating Excel export: {e}")
            raise