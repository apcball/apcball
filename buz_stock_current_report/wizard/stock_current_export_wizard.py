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
        domain=[('usage', 'in', ['internal', 'transit'])],
        help='Leave empty to include all internal and transit locations'
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
        Retrieve HISTORICAL stock data at a specific date.

        Instead of reading from stock_quant (always current), this computes
        stock quantities at date_to from done stock moves — so users can
        see what stock levels were at any past date.

        Also shows incoming/outgoing movements that happened WITHIN the
        selected date_from … date_to range.
        """
        _logger.info(f"Fetching historical stock data at date_to={date_to}, date_from={date_from}")

        has_cost_access = self.env.user.has_group('buz_stock_current_report.group_stock_cost_viewer')

        # ────────────────────────────────────────────────────────────
        # Position-based parameters throughout (%s).
        #
        # Placeholder order:
        #   %s = snapshot-to  (×2 — stock_at_end: incoming + outgoing)
        #   %s = snapshot-from(×2 — stock_at_begin: incoming + outgoing)
        #   %s = date_from    (×2 — period_movements incoming + outgoing)
        #   %s = date_to      (×2 — period_movements incoming + outgoing)
        #   then optional: location_ids, product_ids, category_ids
        # ────────────────────────────────────────────────────────────

        cost_select = """
            ,
            COALESCE(pt.list_price, 0) AS unit_cost,
            COALESCE(sde.quantity, 0) * COALESCE(pt.list_price, 0) AS total_value
        """ if has_cost_access else """
            ,
            0 AS unit_cost,
            0 AS total_value
        """

        query = f"""
            WITH stock_at_end AS (
                -- Stock quantity at date_to (ending balance)
                SELECT
                    location_id,
                    product_id,
                    SUM(net_qty) AS quantity
                FROM (
                    SELECT
                        sml.location_dest_id AS location_id,
                        sml.product_id,
                        SUM(sml.quantity) AS net_qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state = 'done'
                      AND sm.date::date <= %s
                      AND sml.location_dest_id IS NOT NULL
                    GROUP BY sml.location_dest_id, sml.product_id
                    UNION ALL
                    SELECT
                        sml.location_id AS location_id,
                        sml.product_id,
                        -SUM(sml.quantity) AS net_qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state = 'done'
                      AND sm.date::date <= %s
                      AND sml.location_id IS NOT NULL
                    GROUP BY sml.location_id, sml.product_id
                ) sub
                GROUP BY location_id, product_id
            ),
            stock_at_begin AS (
                -- Stock quantity at date_from (beginning / "ยอดยกมา")
                SELECT
                    location_id,
                    product_id,
                    SUM(net_qty) AS quantity
                FROM (
                    SELECT
                        sml.location_dest_id AS location_id,
                        sml.product_id,
                        SUM(sml.quantity) AS net_qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state = 'done'
                      AND sm.date::date <= %s
                      AND sml.location_dest_id IS NOT NULL
                    GROUP BY sml.location_dest_id, sml.product_id
                    UNION ALL
                    SELECT
                        sml.location_id AS location_id,
                        sml.product_id,
                        -SUM(sml.quantity) AS net_qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state = 'done'
                      AND sm.date::date <= %s
                      AND sml.location_id IS NOT NULL
                    GROUP BY sml.location_id, sml.product_id
                ) sub
                GROUP BY location_id, product_id
            ),
            period_movements AS (
                -- Movements that happened WITHIN date_from .. date_to
                SELECT
                    location_id,
                    product_id,
                    SUM(in_qty) AS incoming,
                    SUM(out_qty) AS outgoing
                FROM (
                    SELECT
                        sml.location_dest_id AS location_id,
                        sml.product_id,
                        SUM(sml.quantity) AS in_qty,
                        0 AS out_qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state = 'done'
                      AND sm.date::date >= %s
                      AND sm.date::date <= %s
                      AND sml.location_dest_id IS NOT NULL
                    GROUP BY sml.location_dest_id, sml.product_id
                    UNION ALL
                    SELECT
                        sml.location_id AS location_id,
                        sml.product_id,
                        0 AS in_qty,
                        SUM(sml.quantity) AS out_qty
                    FROM stock_move_line sml
                    JOIN stock_move sm ON sm.id = sml.move_id
                    WHERE sm.state = 'done'
                      AND sm.date::date >= %s
                      AND sm.date::date <= %s
                      AND sml.location_id IS NOT NULL
                    GROUP BY sml.location_id, sml.product_id
                ) sub2
                GROUP BY location_id, product_id
            )
            SELECT
                ROW_NUMBER() OVER (ORDER BY sl.name, pt.name) AS id,
                COALESCE(sdb.quantity, 0) AS begin_qty,    -- ยอดยกมา  (stock at date_from)
                COALESCE(sde.quantity, 0) AS end_qty,      -- คงเหลือ   (stock at date_to)
                COALESCE(pm.incoming, 0) AS incoming,      -- ขาเข้า
                COALESCE(pm.outgoing, 0) AS outgoing,      -- ขาออก
                sde.product_id,
                sde.location_id,
                pt.categ_id AS category_id,
                pt.uom_id,
                sl.usage AS location_usage,
                CASE
                    WHEN sl.usage = 'internal' THEN 'Internal'
                    WHEN sl.usage = 'transit' THEN 'Transit'
                    WHEN sl.usage = 'production' THEN 'Production'
                    WHEN sl.usage = 'inventory' THEN 'Inventory'
                    ELSE sl.usage
                END AS location_type_name
                {cost_select}
            FROM stock_at_end sde
            LEFT JOIN stock_at_begin sdb
                ON sdb.location_id = sde.location_id
               AND sdb.product_id = sde.product_id
            JOIN product_product pp ON pp.id = sde.product_id
            JOIN product_template pt ON pt.id = pp.product_tmpl_id
            JOIN stock_location sl ON sl.id = sde.location_id
            LEFT JOIN period_movements pm
                ON pm.location_id = sde.location_id
               AND pm.product_id = sde.product_id
            WHERE sl.usage IN ('internal', 'transit')
              AND sde.quantity != 0
        """

        # Build params list (positional)
        # 4 params for stock_at_end + stock_at_begin
        # 4 params for period_movements (from, to ×2)
        params = [
            date_to, date_to,       # stock_at_end (incoming, outgoing)
            date_from, date_from,   # stock_at_begin (incoming, outgoing)
            date_from, date_to,     # period_movements incoming (from, to)
            date_from, date_to,     # period_movements outgoing (from, to)
        ]

        # Add optional filters
        if location_ids:
            query += f" AND sde.location_id IN ({','.join(['%s'] * len(location_ids))})"
            params.extend(location_ids)
        if product_ids:
            query += f" AND sde.product_id IN ({','.join(['%s'] * len(product_ids))})"
            params.extend(product_ids)
        if category_ids:
            query += f" AND pt.categ_id IN ({','.join(['%s'] * len(category_ids))})"
            params.extend(category_ids)

        query += " ORDER BY sl.name, pt.name"

        self.env.cr.execute(query, params)
        results = self.env.cr.dictfetchall()
        _logger.info(f"Retrieved {len(results)} historical stock records (date_to={date_to})")
        return results
