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
    category_id = fields.Many2one('product.category', string='Category', readonly=True)
    uom_id = fields.Many2one('uom.uom', string='UoM', readonly=True)
    quantity = fields.Float('On Hand', readonly=True, digits='Product Unit of Measure')
    free_to_use = fields.Float('Free to Use', readonly=True, digits='Product Unit of Measure')
    incoming = fields.Float('Incoming', readonly=True, digits='Product Unit of Measure')
    outgoing = fields.Float('Outgoing', readonly=True, digits='Product Unit of Measure')
    unit_cost = fields.Float('Unit Cost', readonly=True)
    total_value = fields.Float('Total Value', readonly=True)

    stock_date = fields.Date(string="Stock Date", default=fields.Date.context_today)

    def init(self):
        # view basic real-time stock with cost from product and incoming/outgoing movements
        _logger.info("Initializing stock.current.report view")
        tools.drop_view_if_exists(self._cr, self._table)
        try:
            _logger.info("Creating stock.current.report view")
            self._cr.execute(f"""
                CREATE OR REPLACE VIEW {self._table} AS (
                    SELECT
                        sq.id AS id,
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
                    WHERE sl.usage = 'internal'
                )
            """)
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