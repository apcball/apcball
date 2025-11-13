from odoo import models, fields, api
import logging
_logger = logging.getLogger(__name__)

class StockCurrentExportWizard(models.TransientModel):
    _name = 'stock.current.export.wizard'
    _description = 'Export Current Stock to Excel'

    # Date range filters
    date_from = fields.Date(string="Date From", required=True, default=fields.Date.context_today)
    date_to = fields.Date(string="Date To", required=True, default=fields.Date.context_today)
    
    # Location filter
    location_ids = fields.Many2many(
        'stock.location',
        'stock_export_wizard_location_rel',
        'wizard_id',
        'location_id',
        string='Locations',
        domain=[('usage', '=', 'internal')],
        help='Leave empty to include all internal locations'
    )
    
    # Product filter
    product_ids = fields.Many2many(
        'product.product',
        'stock_export_wizard_product_rel',
        'wizard_id',
        'product_id',
        string='Products',
        help='Leave empty to include all products'
    )
    
    # Product Category filter
    category_ids = fields.Many2many(
        'product.category',
        'stock_export_wizard_category_rel',
        'wizard_id',
        'category_id',
        string='Product Categories',
        help='Leave empty to include all categories'
    )

    def action_export_excel(self):
        """Export filtered stock report to Excel"""
        _logger.info(f"Exporting stock report with filters - Date: {self.date_from} to {self.date_to}")
        try:
            # Prepare filter data
            filter_data = {
                'date_from': self.date_from,
                'date_to': self.date_to,
                'location_ids': self.location_ids.ids if self.location_ids else [],
                'product_ids': self.product_ids.ids if self.product_ids else [],
                'category_ids': self.category_ids.ids if self.category_ids else [],
            }
            
            report_action = self.env.ref(
                'buz_stock_current_report.action_report_stock_current_xlsx'
            ).report_action(self, data=filter_data)
            _logger.info("Successfully generated Excel export action")
            return report_action
        except Exception as e:
            _logger.error(f"Error generating Excel export: {e}")
            raise

    @api.model
    def get_filtered_stock_data(self, date_from, date_to, location_ids=None, product_ids=None, category_ids=None):
        """
        Retrieve stock data filtered by date range, locations, products, and categories
        """
        _logger.info("Fetching filtered stock data")
        
        # Check if user has cost viewing permissions
        has_cost_access = self.env.user.has_group('buz_stock_current_report.group_stock_cost_viewer')
        
        # Build query based on user permissions
        if has_cost_access:
            query = """
                SELECT
                    sq.id,
                    sq.product_id,
                    sq.location_id,
                    pt.categ_id AS category_id,
                    pt.uom_id,
                    COALESCE(sq.quantity, 0) AS quantity,
                    COALESCE(sq.quantity, 0) AS free_to_use,
                    COALESCE(incoming.qty, 0) AS incoming,
                    COALESCE(outgoing.qty, 0) AS outgoing,
                    COALESCE(pt.list_price, 0) AS unit_cost,
                    COALESCE(sq.quantity, 0) * COALESCE(pt.list_price, 0) AS total_value
                FROM stock_quant sq
                JOIN product_product pp ON pp.id = sq.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                JOIN stock_location sl ON sl.id = sq.location_id
                LEFT JOIN (
                    SELECT
                        sml.location_dest_id,
                        sml.product_id,
                        SUM(sml.quantity) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                    AND sml.location_dest_id IS NOT NULL
                    AND sm.date::date >= %s AND sm.date::date <= %s
                    GROUP BY sml.location_dest_id, sml.product_id
                ) incoming ON incoming.location_dest_id = sq.location_id AND incoming.product_id = sq.product_id
                LEFT JOIN (
                    SELECT
                        sml.location_id,
                        sml.product_id,
                        SUM(sml.quantity) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                    AND sml.location_id IS NOT NULL
                    AND sm.date::date >= %s AND sm.date::date <= %s
                    GROUP BY sml.location_id, sml.product_id
                ) outgoing ON outgoing.location_id = sq.location_id AND outgoing.product_id = sq.product_id
                WHERE sl.usage = 'internal'
            """
        else:
            query = """
                SELECT
                    sq.id,
                    sq.product_id,
                    sq.location_id,
                    pt.categ_id AS category_id,
                    pt.uom_id,
                    COALESCE(sq.quantity, 0) AS quantity,
                    COALESCE(sq.quantity, 0) AS free_to_use,
                    COALESCE(incoming.qty, 0) AS incoming,
                    COALESCE(outgoing.qty, 0) AS outgoing,
                    0 AS unit_cost,
                    0 AS total_value
                FROM stock_quant sq
                JOIN product_product pp ON pp.id = sq.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                JOIN stock_location sl ON sl.id = sq.location_id
                LEFT JOIN (
                    SELECT
                        sml.location_dest_id,
                        sml.product_id,
                        SUM(sml.quantity) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                    AND sml.location_dest_id IS NOT NULL
                    AND sm.date::date >= %s AND sm.date::date <= %s
                    GROUP BY sml.location_dest_id, sml.product_id
                ) incoming ON incoming.location_dest_id = sq.location_id AND incoming.product_id = sq.product_id
                LEFT JOIN (
                    SELECT
                        sml.location_id,
                        sml.product_id,
                        SUM(sml.quantity) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                    AND sml.location_id IS NOT NULL
                    AND sm.date::date >= %s AND sm.date::date <= %s
                    GROUP BY sml.location_id, sml.product_id
                ) outgoing ON outgoing.location_id = sq.location_id AND outgoing.product_id = sq.product_id
                WHERE sl.usage = 'internal'
            """
        
        params = [date_from, date_to, date_from, date_to]
        
        # Add location filter
        if location_ids:
            query += f" AND sq.location_id IN ({','.join(['%s'] * len(location_ids))})"
            params.extend(location_ids)
        
        # Add product filter
        if product_ids:
            query += f" AND sq.product_id IN ({','.join(['%s'] * len(product_ids))})"
            params.extend(product_ids)
        
        # Add category filter
        if category_ids:
            query += f" AND pt.categ_id IN ({','.join(['%s'] * len(category_ids))})"
            params.extend(category_ids)
        
        query += " ORDER BY sl.name, pt.name"
        
        self.env.cr.execute(query, params)
        results = self.env.cr.dictfetchall()
        _logger.info(f"Retrieved {len(results)} filtered stock records")
        return results