from odoo import models, fields, tools, api
import logging
_logger = logging.getLogger(__name__)

class StockCurrentReport(models.Model):
    _name = 'stock.current.report'
    _description = 'Current Stock Report (by Date)'
    _auto = False
    _order = 'location_id, product_id'

    product_id = fields.Many2one('product.product', string='Product', readonly=True)
    location_id = fields.Many2one('stock.location', string='Location', readonly=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse', readonly=True)
    category_id = fields.Many2one('product.category', string='Category', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    quantity = fields.Float('On Hand', readonly=True, digits=(16, 2))
    free_to_use = fields.Float('Free to Use', readonly=True, digits='Product Unit of Measure')
    incoming = fields.Float('Incoming', readonly=True, digits='Product Unit of Measure')
    outgoing = fields.Float('Outgoing', readonly=True, digits='Product Unit of Measure')
    unit_cost = fields.Float('Unit Cost', readonly=True, groups='buz_stock_current_report.group_stock_cost_viewer')
    total_value = fields.Float('Total Value', readonly=True, groups='buz_stock_current_report.group_stock_cost_viewer')
    location_usage = fields.Selection([
        ('internal', 'Internal'),
        ('production', 'Production'),
        ('inventory', 'Inventory'),
        ('supplier', 'Supplier'),
        ('customer', 'Customer'),
        ('transit', 'Transit'),
    ], string='Location Usage', readonly=True)
    location_type_name = fields.Char(string='Location Type', readonly=True)
    product_selection = fields.Boolean(string='Select', default=False)

    stock_date = fields.Date(string="Stock Date", default=fields.Date.context_today)

    def action_view_product_moves(self):
        """Action to view stock moves for this product/location"""
        _logger.info(f"action_view_product_moves called with ids: {self.ids}")
        
        # Handle case where no record is selected
        if not self or len(self) == 0:
            _logger.warning("action_view_product_moves called with no record")
            from odoo.exceptions import UserError
            raise UserError('Please select a product to view moves')
        
        # Get the first record
        record = self[0]
        
        return {
            'name': 'Stock Moves',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.move.line',
            'view_mode': 'tree,form',
            'domain': [
                ('product_id', '=', record.product_id.id),
                '|', ('location_id', '=', record.location_id.id),
                ('location_dest_id', '=', record.location_id.id)
            ],
            'context': {'default_product_id': record.product_id.id},
        }

    def action_transfer_single_product(self):
        """Action to transfer a single product"""
        _logger.info(f"action_transfer_single_product called with ids: {self.ids}, context: {self.env.context}")
        
        # Handle case where no record is selected
        if not self or len(self) == 0:
            _logger.warning("action_transfer_single_product called with no record")
            from odoo.exceptions import UserError
            raise UserError('Please select a product to transfer')
        
        # Get the first record
        record = self[0]
        _logger.info(f"Transferring product: {record.product_id.name} from location: {record.location_id.name}")
        
        # Prepare product data for transfer wizard
        product_data = {
            'productId': record.product_id.id,
            'locationId': record.location_id.id,
            'quantity': record.quantity,
            'uomId': record.uom_id.id,
            'productName': record.product_id.name,
            'locationName': record.location_id.name
        }
        
        return {
            'name': 'Transfer Product',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.current.transfer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_selected_products': [product_data]
            }
        }

    def action_bulk_transfer(self):
        """Action for bulk transfer of selected products"""
        _logger.info(f"action_bulk_transfer called with ids: {self.ids}, active_ids: {self.env.context.get('active_ids')}")
        
        # Get selected IDs from context
        active_ids = self.env.context.get('active_ids', [])
        
        if not active_ids:
            _logger.warning("No active_ids in context for bulk transfer")
            from odoo.exceptions import UserError
            raise UserError('Please select at least one product to transfer')
        
        selected_records = self.env['stock.current.report'].search([
            ('id', 'in', active_ids)
        ])
        
        if not selected_records:
            from odoo.exceptions import UserError
            raise UserError('Please select at least one product to transfer')
        
        _logger.info(f"Bulk transferring {len(selected_records)} records")
        
        products_data = []
        for record in selected_records:
            product_data = {
                'productId': record.product_id.id,
                'locationId': record.location_id.id,
                'quantity': record.quantity,
                'uomId': record.uom_id.id,
                'productName': record.product_id.name,
                'locationName': record.location_id.name
            }
            _logger.info(f"Adding to bulk transfer: {product_data}")
            products_data.append(product_data)
        
        _logger.info(f"Total products for transfer: {len(products_data)}")
        
        return {
            'name': 'Bulk Transfer',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.current.transfer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_selected_products': products_data
            }
        }

    def action_open_transfer_simple(self):
        """Simple action to open transfer wizard - menu entry point"""
        return {
            'name': 'Create Transfer',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.current.transfer.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {}
        }

    def action_open_record(self):
        """Action to open the form view of the current record"""
        self.ensure_one()
        return {
            'name': 'Stock Details',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.current.report',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def init(self):
        # view basic real-time stock with cost from product and incoming/outgoing movements
        _logger.info("Initializing stock.current.report view")
        tools.drop_view_if_exists(self._cr, self._table)
        try:
            # First, let's check what columns are available in product_template
            _logger.info("Checking available price columns in product_template")
            self._cr.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'product_template'
                AND column_name LIKE '%price%'
                ORDER BY column_name
            """)
            price_columns = self._cr.fetchall()
            available_columns = [col[0] for col in price_columns]
            _logger.info(f"Available price columns: {available_columns}")
            
            # Determine which price column to use - prioritize list_price for Odoo 17
            price_column = 'list_price'  # Default for Odoo 17
            if 'list_price' not in available_columns:
                if 'standard_price' in available_columns:
                    price_column = 'standard_price'
                    _logger.warning("list_price not found, falling back to standard_price")
                else:
                    _logger.error("No suitable price column found! Available: %s", available_columns)
                    raise Exception("No suitable price column found in product_template")
            
            _logger.info(f"Using price column: {price_column}")
            
            _logger.info("Creating stock.current.report view")
            sql_query = f"""
                CREATE OR REPLACE VIEW {self._table} AS (
                    SELECT
                        sq.id AS id,
                        sq.product_id,
                        sq.location_id,
                        COALESCE(sl.warehouse_id, w.id) AS warehouse_id,
                        pt.categ_id AS category_id,
                        pt.uom_id,
                        COALESCE(sq.quantity, 0) AS quantity,
                        COALESCE(sq.quantity, 0) + COALESCE(incoming.qty, 0) - COALESCE(outgoing.qty, 0) AS free_to_use,
                        COALESCE(incoming.qty, 0) AS incoming,
                        COALESCE(outgoing.qty, 0) AS outgoing,
                        COALESCE(pt.{price_column}, 0) AS unit_cost,
                        COALESCE(sq.quantity, 0) * COALESCE(pt.{price_column}, 0) AS total_value,
                        sl.usage AS location_usage,
                        CASE
                            WHEN sl.usage = 'internal' THEN 'Internal'
                            WHEN sl.usage = 'production' THEN 'Production'
                            WHEN sl.usage = 'inventory' THEN 'Inventory'
                            WHEN sl.usage = 'transit' THEN 'Transit'
                            ELSE sl.usage
                        END AS location_type_name,
                        false AS product_selection,
                        CURRENT_DATE AS stock_date
                    FROM stock_quant sq
                    JOIN product_product pp ON pp.id = sq.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    JOIN stock_location sl ON sl.id = sq.location_id
                    LEFT JOIN stock_warehouse w ON (
                        sl.id = w.lot_stock_id OR
                        sl.id = w.wh_input_stock_loc_id OR
                        sl.id = w.wh_output_stock_loc_id OR
                        sl.id = w.wh_pack_stock_loc_id OR
                        sl.id = w.wh_qc_stock_loc_id
                    )
                    LEFT JOIN (
                        SELECT
                            sml.location_dest_id,
                            sml.product_id,
                            SUM(sml.quantity) AS qty
                        FROM stock_move_line sml
                        JOIN stock_move sm ON sm.id = sml.move_id
                        WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                        AND sml.location_dest_id IS NOT NULL
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
                        GROUP BY sml.location_id, sml.product_id
                    ) outgoing ON outgoing.location_id = sq.location_id AND outgoing.product_id = sq.product_id
                    WHERE sl.usage IN ('internal', 'production', 'inventory', 'transit')
                )
            """
            _logger.info(f"SQL Query to be executed (using {price_column}):\n{sql_query}")
            self._cr.execute(sql_query)
            _logger.info(f"Successfully created {self._table} view")
        except Exception as e:
            _logger.error(f"Error creating {self._table} view: {e}")
            raise

    @api.model
    def check_access(self):
        """Debug method to check if model is accessible"""
        try:
            self._cr.execute(f"SELECT COUNT(*) FROM {self._table} LIMIT 1")
            count = self._cr.fetchone()[0]
            _logger.info(f"Model {self._table} is accessible, found {count} records")
            return True
        except Exception as e:
            _logger.error(f"Error accessing model {self._table}: {e}")
            return False

    @api.model
    def compute_stock_at_date(self, date):
        """Return quantities at a specific date (historical)"""
        query = f"""
            SELECT
                sml.product_id,
                sml.location_id,
                pt.uom_id,
                sum(
                    CASE
                        WHEN sml.location_dest_id IN (
                            SELECT id FROM stock_location WHERE usage = 'internal'
                        )
                        THEN sml.quantity
                        ELSE 0
                    END
                    -
                    CASE
                        WHEN sml.location_id IN (
                            SELECT id FROM stock_location WHERE usage = 'internal'
                        )
                        THEN sml.quantity
                        ELSE 0
                    END
                ) AS quantity
            FROM stock_move_line sml
            JOIN stock_move sm ON sm.id = sml.move_id
            JOIN product_product pp ON pp.id = sml.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            WHERE sm.date <= %s
            AND sm.state = 'done'
            GROUP BY sml.product_id, sml.location_id, pt.uom_id
        """
        self._cr.execute(query, (date,))
        return self._cr.dictfetchall()

    @api.model
    def get_warehouses_with_locations(self):
        """Enhanced method to include both internal and transit locations"""
        query = """
            SELECT
                w.id,
                w.name,
                w.code,
                COUNT(DISTINCT l.id) as location_count,
                COALESCE(SUM(s.total_products), 0) as total_products,
                COALESCE(SUM(s.total_value), 0) as total_value
            FROM stock_warehouse w
            LEFT JOIN stock_location l ON l.warehouse_id = w.id AND l.usage IN ('internal', 'transit') AND l.active = true
            LEFT JOIN (
                SELECT
                    location_id,
                    COUNT(DISTINCT product_id) as total_products,
                    SUM(total_value) as total_value
                FROM stock_current_report
                GROUP BY location_id
            ) s ON s.location_id = l.id
            WHERE w.active = true
            GROUP BY w.id, w.name, w.code
            ORDER BY w.name
        """
        self._cr.execute(query)
        warehouses = self._cr.dictfetchall()
        
        # Get internal locations for each warehouse
        for warehouse in warehouses:
            internal_location_query = """
                SELECT
                    l.id,
                    l.name,
                    l.complete_name,
                    l.usage,
                    COUNT(DISTINCT scr.product_id) as product_count,
                    COALESCE(SUM(scr.quantity), 0) as total_quantity,
                    COALESCE(SUM(scr.total_value), 0) as total_value
                FROM stock_location l
                LEFT JOIN stock_current_report scr ON scr.location_id = l.id
                WHERE l.warehouse_id = %s AND l.usage = 'internal' AND l.active = true
                GROUP BY l.id, l.name, l.complete_name, l.usage
                ORDER BY l.name
            """
            self._cr.execute(internal_location_query, (warehouse['id'],))
            warehouse['internal_locations'] = self._cr.dictfetchall()
            
            # Get transit locations for each warehouse
            transit_location_query = """
                SELECT
                    l.id,
                    l.name,
                    l.complete_name,
                    l.usage,
                    COUNT(DISTINCT scr.product_id) as product_count,
                    COALESCE(SUM(scr.quantity), 0) as total_quantity,
                    COALESCE(SUM(scr.total_value), 0) as total_value
                FROM stock_location l
                LEFT JOIN stock_current_report scr ON scr.location_id = l.id
                WHERE l.warehouse_id = %s AND l.usage = 'transit' AND l.active = true
                GROUP BY l.id, l.name, l.complete_name, l.usage
                ORDER BY l.name
            """
            self._cr.execute(transit_location_query, (warehouse['id'],))
            warehouse['transit_locations'] = self._cr.dictfetchall()
            
            # For backward compatibility, keep the old locations field with internal locations
            warehouse['locations'] = warehouse['internal_locations']
        
        return warehouses

    @api.model
    def get_warehouses_with_internal_locations(self):
        """Deprecated method - use get_warehouses_with_locations instead"""
        return self.get_warehouses_with_locations()

    @api.model
    def get_location_hierarchy(self):
        """Get hierarchical structure of all internal locations"""
        query = """
            WITH RECURSIVE location_tree AS (
                SELECT
                    l.id,
                    l.name,
                    l.complete_name,
                    l.location_id,
                    l.warehouse_id,
                    l.usage,
                    0 as level,
                    ARRAY[l.id] as path
                FROM stock_location l
                WHERE l.location_id IS NULL AND l.usage IN ('internal', 'production', 'inventory', 'transit')
                
                UNION ALL
                
                SELECT
                    child.id,
                    child.name,
                    child.complete_name,
                    child.location_id,
                    child.warehouse_id,
                    child.usage,
                    lt.level + 1,
                    lt.path || child.id
                FROM stock_location child
                JOIN location_tree lt ON child.location_id = lt.id
                WHERE child.usage IN ('internal', 'production', 'inventory', 'transit')
            )
            SELECT
                lt.*,
                w.name as warehouse_name,
                COUNT(DISTINCT scr.product_id) as product_count
            FROM location_tree lt
            LEFT JOIN stock_warehouse w ON w.id = lt.warehouse_id
            LEFT JOIN stock_current_report scr ON scr.location_id = lt.id
            GROUP BY lt.id, lt.name, lt.complete_name, lt.location_id,
                     lt.warehouse_id, lt.usage, lt.level, lt.path, w.name
            ORDER BY lt.path
        """
        self._cr.execute(query)
        return self._cr.dictfetchall()

    @api.model
    def get_warehouse_location_summary(self):
        """Get summary data for warehouse sidebar"""
        warehouses = self.env['stock.warehouse'].search([('active', '=', True)])
        total_warehouses = len(warehouses)
        total_locations = 0
        total_products = 0
        
        for warehouse in warehouses:
            locations = self.env['stock.location'].search([
                ('warehouse_id', '=', warehouse.id),
                ('usage', 'in', ['internal', 'transit']),
                ('active', '=', True)
            ])
            total_locations += len(locations)
            
            for location in locations:
                total_products += self.search_count([('location_id', '=', location.id)])
        
        return {
            'total_warehouses': total_warehouses,
            'total_locations': total_locations,
            'total_products': total_products
        }