# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import fields, models, tools

# Thailand has no DST, so Bangkok is always a fixed UTC+7 offset.
BANGKOK_UTC_OFFSET = timedelta(hours=7)


class StockFifoValuationReport(models.Model):
    """Warehouse valuation summary sourced directly from stock.valuation.layer
    (not from stock.move + averaged cost), so it stays consistent with the
    FIFO engine in stock_fifo_by_location (remaining_qty / origin_remaining_qty).
    """
    _name = "stock.fifo.valuation.report"
    _description = "Stock FIFO Valuation Report"
    _auto = False

    product_id = fields.Many2one(comodel_name="product.product", readonly=True)
    default_code = fields.Char(
        related="product_id.default_code", string="Internal Reference",
        readonly=True, store=False)
    product_uom = fields.Many2one(comodel_name="uom.uom", readonly=True)
    product_category = fields.Many2one(
        comodel_name="product.category", readonly=True)
    warehouse_id = fields.Many2one(comodel_name="stock.warehouse", readonly=True)
    opening_qty = fields.Float(readonly=True)
    opening_value = fields.Float(readonly=True)
    in_qty = fields.Float(readonly=True)
    in_value = fields.Float(readonly=True)
    out_qty = fields.Float(readonly=True)
    out_value = fields.Float(readonly=True)
    landed_cost_value = fields.Float(
        readonly=True,
        help="Value of landed-cost layers (quantity = 0) added in the period. "
             "These carry no quantity, so they belong to neither In nor Out, "
             "but they do move Ending Value.")
    revaluation_value = fields.Float(
        readonly=True,
        help="Value of manual revaluation layers (quantity = 0, no landed "
             "cost document) posted in the period.")
    ending_qty = fields.Float(readonly=True)
    ending_value = fields.Float(readonly=True)
    remaining_value_check = fields.Float(
        readonly=True,
        help="SUM(remaining_value) of layers that are still open TODAY, "
             "restricted to those created before date_to. remaining_qty / "
             "remaining_value are mutated in place by the FIFO engine and "
             "there is no point-in-time snapshot, so this column only "
             "reconciles against Ending Value when date_to is today. On a "
             "back-dated run it always understates and should be ignored.")

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        view_sql = "CREATE or REPLACE VIEW " + self._table + """ as (
            SELECT
                0 as id,
                0 as product_id,
                0 as product_uom,
                0 as product_category,
                0 as warehouse_id,
                0.0 as opening_qty,
                0.0 as opening_value,
                0.0 as in_qty,
                0.0 as in_value,
                0.0 as out_qty,
                0.0 as out_value,
                0.0 as landed_cost_value,
                0.0 as revaluation_value,
                0.0 as ending_qty,
                0.0 as ending_value,
                0.0 as remaining_value_check
            FROM product_product
            LIMIT 0
        )"""
        self.env.cr.execute(view_sql)

    def _get_warehouse_ids(self, warehouse_id):
        if warehouse_id:
            return tuple(warehouse_id.ids)
        warehouses = tuple(self.env["stock.warehouse"].search([]).ids)
        return warehouses or (-1,)

    def _get_warehouse_clause(self, warehouse_id):
        """SQL predicate for the warehouse filter.

        A handful of layers carry no warehouse at all (manual revaluations
        posted without a stock move, so there is no location to derive one
        from). `warehouse_id in (...)` silently drops them, which loses real
        value from the report. When the user asked for every warehouse, keep
        them; when a specific warehouse was picked, they are genuinely out of
        scope.
        """
        if warehouse_id:
            return "svl.warehouse_id in %s"
        return "(svl.warehouse_id in %s or svl.warehouse_id is null)"

    def _get_product_category_ids(self, product_category_ids):
        if product_category_ids:
            return tuple(self.env['product.category'].search(
                [('id', 'child_of', product_category_ids.ids)]).ids)
        categs = tuple(self.env["product.category"].search([]).ids)
        return categs or (-1,)

    def _get_product_ids(self, product_ids, product_category_ids):
        if product_ids:
            return tuple(product_ids.ids)
        if product_category_ids:
            products = tuple(self.env['product.product'].search(
                [('categ_id', 'child_of', product_category_ids.ids)]).ids)
            return products or (-1,)
        products = tuple(self.env["product.product"].search([("active", "=", True)]).ids)
        return products or (-1,)

    def _bangkok_day_range_to_utc(self, day_from, day_to):
        utc_lower = datetime.combine(day_from, time.min) - BANGKOK_UTC_OFFSET
        utc_upper = datetime.combine(
            day_to + timedelta(days=1), time.min) - BANGKOK_UTC_OFFSET
        return utc_lower, utc_upper

    def _get_cutoff_date(self):
        """Opening balance cutoff: layers before this date are excluded from
        the report entirely (set via system parameter
        stock_fifo_valuation_report.cutoff_date, e.g. after re-entering
        opening stock)."""
        cutoff = self.env["ir.config_parameter"].sudo().get_param(
            "stock_fifo_valuation_report.cutoff_date")
        return fields.Date.to_date(cutoff) if cutoff else fields.Date.to_date("1900-01-01")

    def init_results(self, filters):
        cutoff_date = self._get_cutoff_date()
        date_from = filters.date_from or fields.Date.to_date("1900-01-01")
        if date_from < cutoff_date:
            date_from = cutoff_date
        date_to = filters.date_to or fields.Date.context_today(self)
        utc_lower, utc_upper = self._bangkok_day_range_to_utc(date_from, date_to)
        utc_cutoff, _ = self._bangkok_day_range_to_utc(cutoff_date, date_to)

        warehouse_ids = self._get_warehouse_ids(filters.warehouse_ids)
        product_category_ids = self._get_product_category_ids(filters.product_category_ids)
        product_ids = self._get_product_ids(filters.product_ids, filters.product_category_ids)
        warehouse_clause = self._get_warehouse_clause(filters.warehouse_ids)

        query_ = """
            SELECT *, (a.opening_value + a.in_value + a.out_value
                    + a.landed_cost_value + a.revaluation_value) as ending_value,
                (a.opening_qty + a.in_qty + a.out_qty) as ending_qty
            FROM (
                SELECT row_number() OVER () as id,
                    svl.product_id,
                    uom_prod.id as product_uom,
                    template.categ_id as product_category,
                    svl.warehouse_id,
                    SUM(CASE WHEN svl.create_date < %s THEN svl.quantity ELSE 0 END) as opening_qty,
                    SUM(CASE WHEN svl.create_date < %s THEN svl.value ELSE 0 END) as opening_value,
                    SUM(CASE WHEN svl.create_date >= %s AND svl.create_date < %s AND svl.quantity > 0
                        THEN svl.quantity ELSE 0 END) as in_qty,
                    SUM(CASE WHEN svl.create_date >= %s AND svl.create_date < %s AND svl.quantity > 0
                        THEN svl.value ELSE 0 END) as in_value,
                    SUM(CASE WHEN svl.create_date >= %s AND svl.create_date < %s AND svl.quantity < 0
                        THEN svl.quantity ELSE 0 END) as out_qty,
                    SUM(CASE WHEN svl.create_date >= %s AND svl.create_date < %s AND svl.quantity < 0
                        THEN svl.value ELSE 0 END) as out_value,
                    SUM(CASE WHEN svl.create_date >= %s AND svl.create_date < %s AND svl.quantity = 0
                        AND svl.stock_landed_cost_id IS NOT NULL
                        THEN svl.value ELSE 0 END) as landed_cost_value,
                    SUM(CASE WHEN svl.create_date >= %s AND svl.create_date < %s AND svl.quantity = 0
                        AND svl.stock_landed_cost_id IS NULL
                        THEN svl.value ELSE 0 END) as revaluation_value,
                    SUM(CASE WHEN svl.create_date < %s AND svl.remaining_qty > 0
                        THEN svl.remaining_value ELSE 0 END) as remaining_value_check
                FROM stock_valuation_layer svl
                    LEFT JOIN product_product product ON svl.product_id = product.id
                    LEFT JOIN product_template template ON product.product_tmpl_id = template.id
                    LEFT JOIN uom_uom uom_prod ON template.uom_id = uom_prod.id
                WHERE
                    """ + warehouse_clause + """
                    and svl.product_id in %s
                    and template.categ_id in %s
                    and svl.create_date >= %s
                    and svl.create_date < %s
                GROUP BY svl.product_id, uom_prod.id, template.categ_id, svl.warehouse_id
                ORDER BY svl.product_id, svl.warehouse_id
            ) as a
        """
        params = (
            utc_lower, utc_lower,
            utc_lower, utc_upper,
            utc_lower, utc_upper,
            utc_lower, utc_upper,
            utc_lower, utc_upper,
            utc_lower, utc_upper,
            utc_lower, utc_upper,
            utc_upper,
            warehouse_ids, product_ids, product_category_ids,
            utc_cutoff, utc_upper,
        )

        tools.drop_view_if_exists(self._cr, self._table)
        create_sql = "CREATE VIEW " + self._table + " as (" + query_ + ")"
        res = self._cr.execute(create_sql, params)
        return res

    def report_details(self):
        filters = dict(self._context.get("filters") or {})
        filters["product_ids"] = [(6, 0, self.product_id.ids)]
        # An unassigned-warehouse row has no warehouse to narrow to; keep the
        # wizard's own warehouse filter so the drilldown isn't empty.
        if self.warehouse_id:
            filters["warehouse_ids"] = [(6, 0, self.warehouse_id.ids)]
        return self.env["stock.fifo.valuation.details.report"].view_report_details(filters)
