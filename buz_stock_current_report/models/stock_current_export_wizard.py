from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class StockCurrentExportWizard(models.TransientModel):
    _name = 'stock.current.export.wizard'
    _description = 'Stock Current Export Wizard'

    date_from = fields.Date(string='Date From', default=fields.Date.context_today)
    date_to = fields.Date(string='Date To', default=fields.Date.context_today)
    location_ids = fields.Many2many(
        'stock.location',
        string='Locations',
        domain="[('usage', '=', 'internal')]"
    )
    product_ids = fields.Many2many('product.product', string='Products')
    category_ids = fields.Many2many('product.category', string='Categories')

    def get_filtered_stock_data(self):
        """Get filtered stock data based on wizard filters"""
        # Build domain based on filters
        domain = []
        
        if self.date_from:
            domain.append(('stock_date', '>=', self.date_from))
        if self.date_to:
            domain.append(('stock_date', '<=', self.date_to))
        if self.location_ids:
            domain.append(('location_id', 'in', self.location_ids.ids))
        if self.product_ids:
            domain.append(('product_id', 'in', self.product_ids.ids))
        if self.category_ids:
            domain.append(('category_id', 'in', self.category_ids.ids))
        
        # Get stock data
        stock_records = self.env['stock.current.report'].search(domain)
        
        # Prepare data for export
        data = []
        for record in stock_records:
            data.append({
                'warehouse': record.warehouse_id.name or '',
                'location': record.location_id.name or '',
                'product': record.product_id.name or '',
                'product_code': record.product_id.default_code or '',
                'category': record.category_id.name or '',
                'uom': record.uom_id.name or '',
                'quantity': record.quantity,
                'free_to_use': record.free_to_use,
                'incoming': record.incoming,
                'outgoing': record.outgoing,
                'unit_cost': record.unit_cost,
                'total_value': record.total_value,
                'location_usage': record.location_usage,
                'stock_date': record.stock_date,
            })
        
        return data

    def action_export_excel(self):
        """Export current stock to Excel"""
        self.ensure_one()
        
        # Get filtered stock data
        data = self.get_filtered_stock_data()
        
        # Return action for Excel report
        return {
            'type': 'ir.actions.report',
            'report_name': 'buz_stock_current_report.stock_current_report_xlsx',
            'report_type': 'xlsx',
            'data': {
                'stock_data': data,
                'date_from': self.date_from,
                'date_to': self.date_to,
                'filters': {
                    'locations': [loc.name for loc in self.location_ids],
                    'products': [prod.name for prod in self.product_ids],
                    'categories': [cat.name for cat in self.category_ids],
                }
            }
        }