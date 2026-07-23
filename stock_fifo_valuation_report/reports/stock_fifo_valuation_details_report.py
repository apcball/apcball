# -*- coding: utf-8 -*-
from datetime import datetime, time, timedelta

from odoo import api, fields, models, tools

BANGKOK_UTC_OFFSET = timedelta(hours=7)


class StockFifoValuationDetailsReport(models.Model):
    """One row per stock.valuation.layer (not per stock.move), so MO
    consumption can be traced to the exact FIFO layer/origin it drew from.
    """
    _name = "stock.fifo.valuation.details.report"
    _description = "Stock FIFO Valuation Details Report"
    _auto = False

    layer_id = fields.Integer(readonly=True, string="Layer ID")
    create_date = fields.Datetime(readonly=True)
    product_id = fields.Many2one(comodel_name="product.product", readonly=True)
    product_uom = fields.Many2one(comodel_name="uom.uom", readonly=True)
    product_category = fields.Many2one(comodel_name="product.category", readonly=True)
    warehouse_id = fields.Many2one(comodel_name="stock.warehouse", readonly=True)
    quantity = fields.Float(readonly=True)
    unit_cost = fields.Float(readonly=True)
    value = fields.Float(readonly=True)
    remaining_qty = fields.Float(readonly=True)
    remaining_value = fields.Float(readonly=True)
    is_position_layer = fields.Boolean(readonly=True)
    origin_valuation_layer_id = fields.Many2one(
        comodel_name="stock.valuation.layer", readonly=True,
        string="Origin FIFO Layer")
    origin_remaining_qty = fields.Float(readonly=True)
    origin_remaining_value = fields.Float(readonly=True)
    stock_move_id = fields.Many2one(comodel_name="stock.move", readonly=True)
    reference = fields.Char(readonly=True)
    origin = fields.Char(readonly=True)
    partner_id = fields.Many2one(comodel_name="res.partner", readonly=True)
    location_id = fields.Many2one(comodel_name="stock.location", readonly=True)
    location_dest_id = fields.Many2one(comodel_name="stock.location", readonly=True)
    picking_id = fields.Many2one(comodel_name="stock.picking", readonly=True)
    production_id = fields.Many2one(comodel_name="mrp.production", readonly=True)
    stock_landed_cost_id = fields.Many2one(
        comodel_name="stock.landed.cost", readonly=True,
        string="Landed Cost Doc")
    opening_qty = fields.Float(readonly=True)
    opening_value = fields.Float(readonly=True)
    all_in_unit_cost = fields.Float(
        readonly=True,
        help="(layer value + all landed cost value ever added to this "
             "layer) / layer quantity. Only set on the original receipt "
             "row.")
    lc_line_count = fields.Integer(
        readonly=True,
        help="Number of raw landed-cost SVL rows merged into this one "
             "grouped row (per origin layer / warehouse / LC document).")

    @api.depends('reference', 'picking_id.origin')
    def _compute_display_name(self):
        for rec in self:
            name = rec.reference
            if rec.picking_id.origin:
                name = "{} ({})".format(name, rec.picking_id.origin)
            rec.display_name = name or ""

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        view_sql = "CREATE or REPLACE VIEW " + self._table + """ as (
            SELECT
                0 as id,
                0 as layer_id,
                cast(null as timestamp) as create_date,
                0 as product_id,
                0 as product_uom,
                0 as product_category,
                0 as warehouse_id,
                0.0 as quantity,
                0.0 as unit_cost,
                0.0 as value,
                0.0 as remaining_qty,
                0.0 as remaining_value,
                false as is_position_layer,
                0 as origin_valuation_layer_id,
                0.0 as origin_remaining_qty,
                0.0 as origin_remaining_value,
                0 as stock_move_id,
                cast(null as varchar) as reference,
                cast(null as varchar) as origin,
                0 as partner_id,
                0 as location_id,
                0 as location_dest_id,
                0 as picking_id,
                0 as production_id,
                0 as stock_landed_cost_id,
                0.0 as opening_qty,
                0.0 as opening_value,
                0.0 as all_in_unit_cost,
                0 as lc_line_count
            FROM product_product
            LIMIT 0
        )"""
        self.env.cr.execute(view_sql)

    def _bangkok_day_start_to_utc(self, day):
        return datetime.combine(day, time.min) - BANGKOK_UTC_OFFSET

    def _get_cutoff_date(self):
        return self.env["stock.fifo.valuation.report"]._get_cutoff_date()

    def init_results(self, filter_fields):
        cutoff_date = self._get_cutoff_date()
        date_from = filter_fields.date_from or fields.Date.to_date("1900-01-01")
        if date_from < cutoff_date:
            date_from = cutoff_date
        date_to = filter_fields.date_to or fields.Date.context_today(self)

        warehouse_ids = tuple(filter_fields.warehouse_ids.ids) or (-1,)
        product_ids = tuple(filter_fields.product_ids.ids) or (-1,)

        utc_cutoff = self._bangkok_day_start_to_utc(cutoff_date)
        utc_date_from = self._bangkok_day_start_to_utc(date_from)
        utc_date_to_excl = self._bangkok_day_start_to_utc(date_to + timedelta(days=1))

        query_ = """
            SELECT row_number() OVER (ORDER BY a.create_date, a.layer_id) AS id, * FROM (
                SELECT
                    SUM(svl.quantity) AS opening_qty,
                    SUM(svl.value) AS opening_value,
                    NULL AS layer_id,
                    NULL AS create_date,
                    NULL AS product_id,
                    NULL AS product_uom,
                    NULL AS product_category,
                    NULL AS warehouse_id,
                    NULL AS quantity,
                    NULL AS unit_cost,
                    NULL AS value,
                    NULL AS remaining_qty,
                    NULL AS remaining_value,
                    NULL AS is_position_layer,
                    NULL AS origin_valuation_layer_id,
                    NULL AS origin_remaining_qty,
                    NULL AS origin_remaining_value,
                    NULL AS stock_move_id,
                    NULL AS reference,
                    NULL AS origin,
                    NULL AS partner_id,
                    NULL AS location_id,
                    NULL AS location_dest_id,
                    NULL AS picking_id,
                    NULL AS production_id,
                    NULL AS stock_landed_cost_id,
                    NULL::numeric AS all_in_unit_cost,
                    NULL::bigint AS lc_line_count
                FROM stock_valuation_layer svl
                WHERE
                    svl.warehouse_id in %s
                    and svl.product_id in %s
                    and svl.create_date >= %s
                    and svl.create_date < %s
                UNION ALL
                SELECT
                    NULL AS opening_qty,
                    NULL AS opening_value,
                    svl.id AS layer_id,
                    svl.create_date,
                    svl.product_id,
                    uom_prod.id AS product_uom,
                    template.categ_id AS product_category,
                    svl.warehouse_id,
                    svl.quantity,
                    svl.unit_cost,
                    svl.value,
                    svl.remaining_qty,
                    svl.remaining_value,
                    svl.is_position_layer,
                    svl.origin_valuation_layer_id,
                    svl.origin_remaining_qty,
                    svl.origin_remaining_value,
                    svl.stock_move_id,
                    move.reference,
                    move.origin,
                    move.partner_id,
                    move.location_id,
                    move.location_dest_id,
                    move.picking_id,
                    move.production_id,
                    svl.stock_landed_cost_id,
                    CASE WHEN svl.quantity > 0 THEN
                        (svl.value + COALESCE((
                            SELECT SUM(lc2.value) FROM stock_valuation_layer lc2
                            WHERE lc2.origin_valuation_layer_id = svl.id
                                AND lc2.stock_landed_cost_id IS NOT NULL
                        ), 0)) / svl.quantity
                    ELSE NULL END AS all_in_unit_cost,
                    NULL::bigint AS lc_line_count
                FROM stock_valuation_layer svl
                    LEFT JOIN stock_move move ON svl.stock_move_id = move.id
                    LEFT JOIN product_product product ON svl.product_id = product.id
                    LEFT JOIN product_template template ON product.product_tmpl_id = template.id
                    LEFT JOIN uom_uom uom_prod ON template.uom_id = uom_prod.id
                WHERE
                    svl.stock_landed_cost_id IS NULL
                    and svl.warehouse_id in %s
                    and svl.product_id in %s
                    and svl.create_date >= %s
                    and svl.create_date < %s
                UNION ALL
                SELECT
                    NULL AS opening_qty,
                    NULL AS opening_value,
                    MIN(svl.id) AS layer_id,
                    MAX(svl.create_date) AS create_date,
                    svl.product_id,
                    uom_prod.id AS product_uom,
                    template.categ_id AS product_category,
                    svl.warehouse_id,
                    0.0 AS quantity,
                    NULL AS unit_cost,
                    SUM(svl.value) AS value,
                    NULL AS remaining_qty,
                    NULL AS remaining_value,
                    NULL AS is_position_layer,
                    svl.origin_valuation_layer_id,
                    NULL AS origin_remaining_qty,
                    NULL AS origin_remaining_value,
                    NULL AS stock_move_id,
                    lc.name AS reference,
                    NULL AS origin,
                    NULL AS partner_id,
                    NULL AS location_id,
                    NULL AS location_dest_id,
                    NULL AS picking_id,
                    NULL AS production_id,
                    svl.stock_landed_cost_id,
                    NULL::numeric AS all_in_unit_cost,
                    count(*) AS lc_line_count
                FROM stock_valuation_layer svl
                    LEFT JOIN stock_landed_cost lc ON svl.stock_landed_cost_id = lc.id
                    LEFT JOIN product_product product ON svl.product_id = product.id
                    LEFT JOIN product_template template ON product.product_tmpl_id = template.id
                    LEFT JOIN uom_uom uom_prod ON template.uom_id = uom_prod.id
                WHERE
                    svl.stock_landed_cost_id IS NOT NULL
                    and svl.warehouse_id in %s
                    and svl.product_id in %s
                    and svl.create_date >= %s
                    and svl.create_date < %s
                GROUP BY svl.product_id, uom_prod.id, template.categ_id,
                    svl.warehouse_id, svl.origin_valuation_layer_id,
                    svl.stock_landed_cost_id, lc.name
            ) AS a
            ORDER BY a.create_date, a.layer_id
        """
        params = (
            warehouse_ids, product_ids, utc_cutoff, utc_date_from,
            warehouse_ids, product_ids, utc_date_from, utc_date_to_excl,
            warehouse_ids, product_ids, utc_date_from, utc_date_to_excl,
        )

        tools.drop_view_if_exists(self._cr, self._table)
        create_sql = "CREATE VIEW " + self._table + " as (" + query_ + ")"
        res = self._cr.execute(create_sql, params)
        return res

    def view_report_details(self, filters):
        report = self.env["stock.fifo.valuation.report.wizard"].create(filters)
        self.env["stock.fifo.valuation.details.report"].init_results(report)
        details = self.env["stock.fifo.valuation.details.report"].search([])
        data = {
            'product_default_code': report.product_ids.default_code,
            'product_name': report.product_ids.name,
            'date_from': report.date_from or None,
            'date_to': report.date_to or fields.Date.context_today(self),
            'warehouse': report.warehouse_ids.mapped('name'),
            'category': report.product_category_ids.mapped('complete_name'),
            'detail_ids': details.ids,
        }
        return self.env.ref(
            'stock_fifo_valuation_report.action_stock_fifo_valuation_details_report_html'
        ).with_context(active_model="stock.fifo.valuation.details.report").report_action(
            details.ids, data=data)
