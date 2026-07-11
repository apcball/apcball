from odoo import models, fields, tools, api
from odoo.exceptions import UserError
import logging
_logger = logging.getLogger(__name__)

class StockCurrentReport(models.Model):
    _name = 'stock.current.report'
    _description = 'Current Stock Report (by Date)'
    _auto = False
    _order = 'sales_qty_90d desc, location_id, product_id'

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
    sale_ok = fields.Boolean(string='Can be Sold', readonly=True)
    price_with_vat = fields.Float('Price incl. VAT', readonly=True, digits=(16, 2))
    name_eng = fields.Char(string='Name (Eng)', readonly=True)
    default_code = fields.Char(string='Internal Reference', readonly=True)
    sku = fields.Char(string='SKU', readonly=True)
    product_name = fields.Char(string='Product Name', compute='_compute_product_name')
    product_tag_ids = fields.Many2many('product.tag', string='Tags', related='product_id.product_tmpl_id.product_tag_ids', readonly=True)
    sales_qty_90d = fields.Float('Sold (90 Days)', readonly=True, digits='Product Unit of Measure',
                                 help='Net quantity delivered to customers in the last 90 days (returns deducted). '
                                      'Used to rank best-selling products first.')

    @api.depends('product_id')
    def _compute_product_name(self):
        for rec in self:
            rec.product_name = rec.product_id.name or ''

    def action_open_product(self):
        """Open the product form from kanban card click"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'res_id': self.product_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_product_moves(self):
        """Action to view stock moves for this product/location"""
        _logger.info(f"action_view_product_moves called with ids: {self.ids}")
        
        # Handle case where no record is selected
        if not self:
            _logger.warning("action_view_product_moves called with no record")
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
        if not self:
            _logger.warning("action_transfer_single_product called with no record")
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
            raise UserError('Please select at least one product to transfer')

        selected_records = self.env['stock.current.report'].search([
            ('id', 'in', active_ids)
        ])

        if not selected_records:
            raise UserError('Please select at least one product to transfer')

        _logger.info(f"Bulk transferring {len(selected_records)} records")

        products_data = []
        for record in selected_records:
            products_data.append({
                'productId': record.product_id.id,
                'locationId': record.location_id.id,
                'quantity': record.quantity,
                'uomId': record.uom_id.id,
                'productName': record.product_id.name,
                'locationName': record.location_id.name
            })
        
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

    def action_open_export_wizard(self):
        """Open the Excel export wizard from the report view"""
        return {
            'name': 'Export to Excel',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.current.export.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {},
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

            # Check if mrp_bom table exists (MRP module installed)
            self._cr.execute("SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'mrp_bom')")
            has_mrp = self._cr.fetchone()[0]
            _logger.info(f"MRP module installed: {has_mrp}")

            # Common field projection (shared by all UNION parts)
            common_fields = f"""
                pt.categ_id AS category_id,
                pt.uom_id,
                COALESCE(pt.{price_column}, 0) AS unit_cost,
                COALESCE(pt.sale_ok, false) AS sale_ok,
                ROUND(COALESCE(pt.{price_column}, 0) * 1.07, 2) AS price_with_vat,
                COALESCE(pt.name_eng, '') AS name_eng,
                COALESCE(pp.default_code, '') AS default_code,
                COALESCE(pt.sku, '') AS sku,
                false AS product_selection,
                CURRENT_DATE AS stock_date,
                COALESCE(psales.qty, 0) AS sales_qty_90d
            """

            base_id = "(SELECT COALESCE(MAX(id), 0) FROM stock_quant)"

            # Shared CTEs: each heavy aggregate is declared once and reused by
            # every UNION part, so PostgreSQL materializes it a single time
            # instead of recomputing it per reference.
            ctes = ["""
                products_with_stock AS (
                    SELECT DISTINCT sq.product_id
                    FROM stock_quant sq
                    JOIN stock_location sl ON sl.id = sq.location_id
                    WHERE sl.usage IN ('internal', 'production', 'inventory', 'transit')
                )
            """, """
                product_sales AS (
                    SELECT sml.product_id,
                           SUM(CASE WHEN dest.usage = 'customer'
                                    THEN sml.quantity ELSE -sml.quantity END) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    JOIN stock_location src ON src.id = sml.location_id
                    JOIN stock_location dest ON dest.id = sml.location_dest_id
                    WHERE sm.state = 'done'
                      AND sm.date >= (CURRENT_DATE - INTERVAL '90 days')
                      AND (dest.usage = 'customer') != (src.usage = 'customer')
                    GROUP BY sml.product_id
                )
            """]

            parts = []

            # Part 1: Products with physical stock
            parts.append(f"""
                SELECT sq.id AS id,
                       sq.product_id,
                       sq.location_id,
                       COALESCE(sl.warehouse_id, w.id) AS warehouse_id,
                       {common_fields},
                       COALESCE(sq.quantity, 0) AS quantity,
                       -- Free to Use is the quantity currently available at this
                       -- location.  Pending incoming/outgoing moves are displayed
                       -- separately and must not change the physical availability.
                       GREATEST(COALESCE(sq.quantity, 0) - COALESCE(sq.reserved_quantity, 0), 0) AS free_to_use,
                       COALESCE(incoming.qty, 0) AS incoming,
                       COALESCE(outgoing.qty, 0) AS outgoing,
                       COALESCE(sq.quantity, 0) * COALESCE(pt.{price_column}, 0) AS total_value,
                       sl.usage AS location_usage,
                       CASE WHEN sl.usage = 'internal' THEN 'Internal'
                            WHEN sl.usage = 'production' THEN 'Production'
                            WHEN sl.usage = 'inventory' THEN 'Inventory'
                            WHEN sl.usage = 'transit' THEN 'Transit'
                            ELSE sl.usage
                       END AS location_type_name
                FROM stock_quant sq
                JOIN product_product pp ON pp.id = sq.product_id
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN product_sales psales ON psales.product_id = pp.id
                JOIN stock_location sl ON sl.id = sq.location_id
                LEFT JOIN stock_warehouse w ON (
                    sl.id = w.lot_stock_id OR sl.id = w.wh_input_stock_loc_id OR
                    sl.id = w.wh_output_stock_loc_id OR sl.id = w.wh_pack_stock_loc_id OR
                    sl.id = w.wh_qc_stock_loc_id)
                LEFT JOIN (
                    SELECT sml.location_dest_id, sml.product_id, SUM(sml.quantity) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                    AND sml.location_dest_id IS NOT NULL
                    GROUP BY sml.location_dest_id, sml.product_id
                ) incoming ON incoming.location_dest_id = sq.location_id AND incoming.product_id = sq.product_id
                LEFT JOIN (
                    SELECT sml.location_id, sml.product_id, SUM(sml.quantity) AS qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state IN ('confirmed', 'assigned', 'partially_available')
                    AND sml.location_id IS NOT NULL
                    GROUP BY sml.location_id, sml.product_id
                ) outgoing ON outgoing.location_id = sq.location_id AND outgoing.product_id = sq.product_id
                WHERE sl.usage IN ('internal', 'production', 'inventory', 'transit')
            """)

            if has_mrp:
                # Part 2: BoM kits available at the exact internal location where
                # every component is available.  Do not aggregate components across
                # locations: a kit can only be prepared where all components exist.
                # Completeness is enforced by requiring one matched stock row per
                # requirement line (COUNT(*) = n_lines) instead of cross-joining
                # every location, which exploded to products x locations.
                ctes.append("""
                    kit_requirement AS (
                        SELECT pp.id AS kit_product_id,
                               bl.bom_id,
                               bl.product_id AS component_id,
                               SUM(bl.product_qty) AS component_qty
                        FROM mrp_bom bom
                        JOIN product_product pp ON pp.product_tmpl_id = bom.product_tmpl_id
                            AND (bom.product_id IS NULL OR bom.product_id = pp.id)
                        JOIN mrp_bom_line bl ON bl.bom_id = bom.id
                        WHERE bom.active = true
                        AND bom.type IN ('normal', 'phantom')
                        AND NOT EXISTS (
                            SELECT 1 FROM products_with_stock ps WHERE ps.product_id = pp.id)
                        GROUP BY pp.id, bl.bom_id, bl.product_id
                    )
                """)
                ctes.append("""
                    kit_requirement_size AS (
                        SELECT kit_product_id, COUNT(*) AS n_lines
                        FROM kit_requirement
                        GROUP BY kit_product_id
                    )
                """)
                ctes.append("""
                    component_stock AS (
                        SELECT sq.product_id,
                               sq.location_id,
                               SUM(GREATEST(COALESCE(sq.quantity, 0) - COALESCE(sq.reserved_quantity, 0), 0)) AS qty
                        FROM stock_quant sq
                        JOIN stock_location sl ON sl.id = sq.location_id
                        WHERE sl.usage = 'internal' AND sl.active = true
                        GROUP BY sq.product_id, sq.location_id
                    )
                """)
                ctes.append("""
                    bom_available_by_location AS (
                        SELECT kr.kit_product_id AS product_id,
                               cs.location_id,
                               MIN(FLOOR(cs.qty / NULLIF(kr.component_qty, 0))) AS bom_qty
                        FROM kit_requirement kr
                        JOIN kit_requirement_size krs ON krs.kit_product_id = kr.kit_product_id
                        JOIN component_stock cs ON cs.product_id = kr.component_id AND cs.qty > 0
                        GROUP BY kr.kit_product_id, cs.location_id, krs.n_lines
                        HAVING COUNT(*) = krs.n_lines
                           AND MIN(FLOOR(cs.qty / NULLIF(kr.component_qty, 0))) > 0
                    )
                """)

                parts.append(f"""
                    UNION ALL
                    SELECT {base_id} + ROW_NUMBER() OVER (ORDER BY bom_l.product_id, bom_l.location_id) AS id,
                           bom_l.product_id,
                           bom_l.location_id,
                           COALESCE(sl.warehouse_id, w.id) AS warehouse_id,
                           {common_fields},
                           bom_l.bom_qty AS quantity,
                           bom_l.bom_qty AS free_to_use,
                           0.0 AS incoming, 0.0 AS outgoing,
                           0.0 AS total_value,
                           'internal'::varchar AS location_usage,
                           'Internal'::varchar AS location_type_name
                    FROM bom_available_by_location bom_l
                    JOIN product_product pp ON pp.id = bom_l.product_id
                    JOIN product_template pt ON pt.id = pp.product_tmpl_id
                    LEFT JOIN product_sales psales ON psales.product_id = pp.id
                    JOIN stock_location sl ON sl.id = bom_l.location_id
                    LEFT JOIN stock_warehouse w ON (
                        sl.id = w.lot_stock_id OR sl.id = w.wh_input_stock_loc_id OR
                        sl.id = w.wh_output_stock_loc_id OR sl.id = w.wh_pack_stock_loc_id OR
                        sl.id = w.wh_qc_stock_loc_id)
                """)
            else:
                ctes.append("""
                    bom_available_by_location AS (
                        SELECT NULL::integer AS product_id,
                               NULL::integer AS location_id,
                               NULL::numeric AS bom_qty
                        WHERE false
                    )
                """)

            # Part 3: Products with neither physical stock nor an available kit
            # location — NULL warehouse, qty=0.
            parts.append(f"""
                UNION ALL
                SELECT {base_id} + (SELECT COUNT(*) FROM bom_available_by_location)
                    + ROW_NUMBER() OVER (ORDER BY pp.id) AS id,
                       pp.id AS product_id,
                       NULL::integer AS location_id,
                       NULL::integer AS warehouse_id,
                       {common_fields},
                       0.0 AS quantity,
                       0.0 AS free_to_use,
                       0.0 AS incoming, 0.0 AS outgoing,
                       0.0 AS total_value,
                       NULL::varchar AS location_usage,
                       ''::varchar AS location_type_name
                FROM product_product pp
                JOIN product_template pt ON pt.id = pp.product_tmpl_id
                LEFT JOIN product_sales psales ON psales.product_id = pp.id
                WHERE NOT EXISTS (
                    SELECT 1 FROM products_with_stock ps WHERE ps.product_id = pp.id)
                AND NOT EXISTS (
                    SELECT 1 FROM bom_available_by_location bl WHERE bl.product_id = pp.id)
            """)

            sql_query = (
                "CREATE OR REPLACE VIEW " + self._table + " AS (\n"
                + "WITH " + ",\n".join(ctes) + "\n"
                + "\n".join(parts) + "\n)"
            )
            _logger.debug(f"SQL Query to be executed (using {price_column}):\n{sql_query}")
            self._cr.execute(sql_query)
            _logger.info(f"Successfully created {self._table} view")
        except Exception as e:
            _logger.error(f"Error creating {self._table} view: {e}")
            raise

    @api.model
    def check_access(self):
        """Debug method to check if model is accessible"""
        try:
            self._cr.execute(f"SELECT 1 FROM {self._table} LIMIT 1")
            self._cr.fetchone()
            _logger.info(f"Model {self._table} is accessible")
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

        # Fetch every warehouse's locations in one pass instead of two
        # queries per warehouse (each of which scanned the report view).
        location_query = """
            SELECT
                l.warehouse_id,
                l.id,
                l.name,
                l.complete_name,
                l.usage,
                COUNT(DISTINCT scr.product_id) as product_count,
                COALESCE(SUM(scr.quantity), 0) as total_quantity,
                COALESCE(SUM(scr.total_value), 0) as total_value
            FROM stock_location l
            LEFT JOIN stock_current_report scr ON scr.location_id = l.id
            WHERE l.warehouse_id IS NOT NULL
              AND l.usage IN ('internal', 'transit')
              AND l.active = true
            GROUP BY l.warehouse_id, l.id, l.name, l.complete_name, l.usage
            ORDER BY l.name
        """
        self._cr.execute(location_query)
        locations_by_warehouse = {}
        for loc in self._cr.dictfetchall():
            bucket = locations_by_warehouse.setdefault(
                loc.pop('warehouse_id'), {'internal': [], 'transit': []})
            bucket[loc['usage']].append(loc)

        for warehouse in warehouses:
            bucket = locations_by_warehouse.get(
                warehouse['id'], {'internal': [], 'transit': []})
            warehouse['internal_locations'] = bucket['internal']
            warehouse['transit_locations'] = bucket['transit']
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
        locations = self.env['stock.location'].search([
            ('warehouse_id', 'in', warehouses.ids),
            ('usage', 'in', ['internal', 'transit']),
            ('active', '=', True)
        ])
        total_products = (
            self.search_count([('location_id', 'in', locations.ids)])
            if locations else 0
        )

        return {
            'total_warehouses': len(warehouses),
            'total_locations': len(locations),
            'total_products': total_products
        }
