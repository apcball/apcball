import itertools
from datetime import datetime, time, timedelta

from odoo import api, fields, models, tools

# Thailand has no DST, so Bangkok is always a fixed UTC+7 offset.
BANGKOK_UTC_OFFSET = timedelta(hours=7)


class ImexInventoryDetailsReport(models.Model):
    _name = "imex.inventory.details.report"
    _description = "Imex Inventory Details Report"
    _auto = False

    date = fields.Datetime(readonly=True)
    product_id = fields.Many2one(comodel_name="product.product", readonly=True)
    product_qty = fields.Float(readonly=True)
    product_uom = fields.Many2one(comodel_name="uom.uom", readonly=True)
    product_category = fields.Many2one(
        comodel_name="product.category", readonly=True)
    unit_cost = fields.Float(readonly=True)
    reference = fields.Char(readonly=True)
    partner_id = fields.Many2one(comodel_name="res.partner", readonly=True)
    origin = fields.Char(readonly=True)
    location_id = fields.Many2one(comodel_name="stock.location", readonly=True)
    location_dest_id = fields.Many2one(
        comodel_name="stock.location", readonly=True)
    report_location_id = fields.Many2one(
        comodel_name="stock.location", readonly=True)
    initial = fields.Float(readonly=True)
    initial_amount = fields.Float(readonly=True)
    product_in = fields.Float(readonly=True)
    product_out = fields.Float(readonly=True)
    picking_id = fields.Many2one(comodel_name="stock.picking", readonly=True)

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""CREATE or REPLACE VIEW %s as (
            SELECT 
                0 as id,
                cast(null as timestamp) as date,
                0 as product_id,
                0.0 as product_qty,
                0 as product_uom,
                0 as product_category,
                0.0 as unit_cost,
                cast(null as varchar) as reference,
                0 as partner_id,
                cast(null as varchar) as origin,
                0 as location_id,
                0 as location_dest_id,
                0 as report_location_id,
                0.0 as initial,
                0.0 as initial_amount,
                0.0 as product_in,
                0.0 as product_out,
                0 as picking_id
            FROM product_product
            LIMIT 0
        )""" % self._table)

    @api.depends('reference','picking_id.origin')
    def _compute_display_name(self):
        for rec in self:
            name = rec.reference
            if rec.picking_id.origin:
                name = "{} ({})".format(name, rec.picking_id.origin)
            rec.display_name = f"{name}"

    def _get_locations(self, location_id):
        if (location_id):
            locations = tuple(self.env["stock.location"].search(
                [("id", "child_of", location_id.ids)]).ids)
        else:
            locations = tuple(self.env["stock.location"].search(
                [("usage", "=", "internal")]).ids)
        if not locations:
            locations = (-1,)
        return locations

    def _bangkok_day_start_to_utc(self, day):
        """UTC instant of 00:00 Bangkok time on `day`, for a sargable
        comparison against move.date (stored as naive UTC) instead of
        wrapping move.date in AT TIME ZONE/CAST."""
        return datetime.combine(day, time.min) - BANGKOK_UTC_OFFSET

    def init_results(self, filter_fields):
        cutoff_date = self.env["imex.inventory.report"]._get_cutoff_date()
        date_from = filter_fields.date_from or fields.Date.to_date("1900-01-01")
        if date_from < cutoff_date:
            date_from = cutoff_date
        date_to = filter_fields.date_to or fields.Date.context_today(self)

        locations = self._get_locations(filter_fields.location_id)
        product_ids = tuple(filter_fields.product_ids.ids)

        utc_cutoff = self._bangkok_day_start_to_utc(cutoff_date)
        utc_date_from = self._bangkok_day_start_to_utc(date_from)
        utc_date_to_excl = self._bangkok_day_start_to_utc(
            date_to + timedelta(days=1))

        # Each move is duplicated into two "legs" tagged by report_location_id
        # (the out leg keyed on location_id, the in leg keyed on
        # location_dest_id), mirroring imex_inventory_report.py's groupby
        # pattern. This lets a transfer between two in-scope locations show
        # up as two lines: an out under the source location, an in under the
        # destination, instead of netting to a single zero-sum row.
        #
        # Within each leg, a move whose stock.move.lines span more than one
        # actual location (e.g. manually edited "Detailed Operations") is
        # further fanned out one row per move line, with quantity split
        # proportional to that line's share of the move's total quantity, so
        # location_id/location_dest_id/report_location_id always reflect the
        # real pick/put location instead of the move header's location.
        mline_join = """
                    LEFT JOIN LATERAL (
                        SELECT sml.location_id, sml.location_dest_id,
                            sml.quantity / NULLIF(mtot.total_qty, 0) AS ratio
                        FROM stock_move_line sml
                            CROSS JOIN LATERAL (
                                SELECT SUM(quantity) AS total_qty
                                FROM stock_move_line
                                WHERE move_id = move.id AND quantity != 0
                            ) mtot
                        WHERE sml.move_id = move.id AND sml.quantity != 0
                            AND mtot.total_qty != 0
                        UNION ALL
                        SELECT move.location_id, move.location_dest_id, 1
                        WHERE NOT EXISTS (
                            SELECT 1 FROM stock_move_line sml2
                            WHERE sml2.move_id = move.id AND sml2.quantity != 0
                            GROUP BY sml2.move_id HAVING SUM(sml2.quantity) != 0
                        )
                    ) mline ON true
        """
        query_ = """
            WITH move_leg AS (
                SELECT
                    move.id as move_id,
                    (move.date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Bangkok') AS date,
                    move.product_id,
                    (move.quantity / uom_move.factor * uom_prod.factor) * mline.ratio as quantity,
                    move.product_uom,
                    template.categ_id as product_category,
                    COALESCE(svl.unit_cost, wh_fallback.wh_unit_cost, 0) as unit_cost,
                    move.reference,
                    move.partner_id,
                    move.origin,
                    mline.location_id as location_id,
                    mline.location_dest_id as location_dest_id,
                    mline.location_id as report_location_id,
                    'out' as leg,
                    move.picking_id
                FROM stock_move move
                    LEFT JOIN (
                        SELECT stock_move_id,
                               CASE WHEN SUM(ABS(quantity)) > 0
                                    THEN SUM(ABS(value)) / SUM(ABS(quantity))
                                    ELSE 0 END as unit_cost
                        FROM stock_valuation_layer
                        WHERE quantity != 0
                        GROUP BY stock_move_id
                    ) svl on move.id = svl.stock_move_id
                    """ + mline_join + """
                    LEFT JOIN stock_location location_i on mline.location_id = location_i.id
                    LEFT JOIN stock_location location_d on mline.location_dest_id = location_d.id
                    LEFT JOIN product_product product on move.product_id = product.id
                        LEFT JOIN product_template template on product.product_tmpl_id = template.id
                    LEFT JOIN uom_uom uom_move on move.product_uom = uom_move.id
                    LEFT JOIN uom_uom uom_prod on template.uom_id = uom_prod.id
                    LEFT JOIN LATERAL (
                        SELECT CASE WHEN SUM(ABS(svl2.quantity)) > 0
                                    THEN SUM(ABS(svl2.value)) / SUM(ABS(svl2.quantity))
                                    ELSE NULL END as wh_unit_cost
                        FROM stock_valuation_layer svl2
                        WHERE svl2.product_id = move.product_id
                            AND svl2.warehouse_id = COALESCE(location_d.warehouse_id, location_i.warehouse_id)
                            AND svl2.create_date <= move.date
                    ) wh_fallback ON true
                WHERE
                    mline.location_id in %s
                    and move.state = 'done'
                    and move.product_id in %s
                    and move.date >= %s
                    and move.date < %s
                UNION ALL
                SELECT
                    move.id as move_id,
                    (move.date AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Bangkok') AS date,
                    move.product_id,
                    (move.quantity / uom_move.factor * uom_prod.factor) * mline.ratio as quantity,
                    move.product_uom,
                    template.categ_id as product_category,
                    COALESCE(svl.unit_cost, wh_fallback.wh_unit_cost, 0) as unit_cost,
                    move.reference,
                    move.partner_id,
                    move.origin,
                    mline.location_id as location_id,
                    mline.location_dest_id as location_dest_id,
                    mline.location_dest_id as report_location_id,
                    'in' as leg,
                    move.picking_id
                FROM stock_move move
                    LEFT JOIN (
                        SELECT stock_move_id,
                               CASE WHEN SUM(ABS(quantity)) > 0
                                    THEN SUM(ABS(value)) / SUM(ABS(quantity))
                                    ELSE 0 END as unit_cost
                        FROM stock_valuation_layer
                        WHERE quantity != 0
                        GROUP BY stock_move_id
                    ) svl on move.id = svl.stock_move_id
                    """ + mline_join + """
                    LEFT JOIN stock_location location_i on mline.location_id = location_i.id
                    LEFT JOIN stock_location location_d on mline.location_dest_id = location_d.id
                    LEFT JOIN product_product product on move.product_id = product.id
                        LEFT JOIN product_template template on product.product_tmpl_id = template.id
                    LEFT JOIN uom_uom uom_move on move.product_uom = uom_move.id
                    LEFT JOIN uom_uom uom_prod on template.uom_id = uom_prod.id
                    LEFT JOIN LATERAL (
                        SELECT CASE WHEN SUM(ABS(svl2.quantity)) > 0
                                    THEN SUM(ABS(svl2.value)) / SUM(ABS(svl2.quantity))
                                    ELSE NULL END as wh_unit_cost
                        FROM stock_valuation_layer svl2
                        WHERE svl2.product_id = move.product_id
                            AND svl2.warehouse_id = COALESCE(location_d.warehouse_id, location_i.warehouse_id)
                            AND svl2.create_date <= move.date
                    ) wh_fallback ON true
                WHERE
                    mline.location_dest_id in %s
                    and move.state = 'done'
                    and move.product_id in %s
                    and move.date >= %s
                    and move.date < %s
            )
            SELECT row_number() OVER (ORDER BY a.report_location_id, a.date, a.reference) AS id, * FROM (
                SELECT
                    (SUM(CASE WHEN leg = 'in' THEN quantity ELSE 0 END)
                    -
                    SUM(CASE WHEN leg = 'out' THEN quantity ELSE 0 END)) AS initial,
                    (SUM(CASE WHEN leg = 'in' THEN quantity * unit_cost ELSE 0 END)
                    -
                    SUM(CASE WHEN leg = 'out' THEN quantity * unit_cost ELSE 0 END)) AS initial_amount,
                    null AS date,
                    null AS product_id,
                    null AS product_qty,
                    null AS product_uom,
                    null AS product_category,
                    null AS unit_cost,
                    null AS reference,
                    null AS partner_id,
                    null AS origin,
                    null AS location_id,
                    null AS location_dest_id,
                    report_location_id,
                    null AS product_in,
                    null AS product_out,
                    null AS picking_id
                FROM move_leg
                WHERE date < %s
                GROUP BY report_location_id
                UNION ALL
                SELECT
                    null as initial, null as initial_amount,
                    date,
                    product_id,
                    quantity,
                    product_uom,
                    product_category,
                    unit_cost,
                    reference,
                    partner_id,
                    origin,
                    location_id,
                    location_dest_id,
                    report_location_id,
                    case when leg = 'in' then quantity end as product_in,
                    case when leg = 'out' then quantity end as product_out,
                    picking_id
                FROM move_leg
                WHERE date >= %s
            ) AS a
            ORDER BY a.report_location_id, a.date, a.reference
            """
        params = (locations,
                  product_ids,
                  utc_cutoff,
                  utc_date_to_excl,
                  locations,
                  product_ids,
                  utc_cutoff,
                  utc_date_to_excl,
                  utc_date_from,
                  utc_date_from)

        tools.drop_view_if_exists(self._cr, self._table)
        view_ddl = "CREATE VIEW {} as ({})".format(self._table, query_)
        res = self._cr.execute(view_ddl, params)
        return res

    def view_report_details(self, filters):
        report = self.env["imex.inventory.report.wizard"].create(filters)
        # The report is rendered as a second, separate HTTP request (the web
        # client opens /report/html/...), so nothing computed here survives
        # into that request. Only the wizard id needs to travel through the
        # report URL - passing the full details recordset ids there (as this
        # report used to) makes the URL grow with the number of stock moves
        # on the product and blows past nginx's request-line size limit
        # (414) for products with heavy transaction history. The wizard
        # record itself carries the filters, so the render-time hook
        # (report.imex_inventory_report.imex_inventory_details_report_html
        # below) can redo the lookup from a single small id.
        return self.env.ref('imex_inventory_report.action_imex_inventory_details_report_html').report_action(report.ids)


class ReportImexInventoryDetailsReportHtml(models.AbstractModel):
    # Must be named exactly "report.<report_name>" - this is the hook Odoo's
    # report engine (ir_actions_report._get_rendering_context) looks up by
    # convention; a _get_report_values defined anywhere else is never called.
    _name = "report.imex_inventory_report.imex_inventory_details_report_html"
    _description = "Imex Inventory Details Report Renderer"

    def _group_details_by_location(self, details):
        """Group an already-fetched details recordset by report_location_id,
        keeping actual recordsets (not id lists) so callers never need to
        re-browse from ids serialized through a report URL."""
        location_groups = []
        for _location_id, group in itertools.groupby(
                details, key=lambda rec: rec.report_location_id.id):
            group_lines = self.env["imex.inventory.details.report"].browse(
                [rec.id for rec in group])
            initial_line = group_lines.filtered(lambda l: not l.product_id)
            lines = group_lines.filtered(lambda l: l.product_id)
            location_groups.append({
                'location_name': group_lines[0].report_location_id.complete_name,
                'initial': initial_line[:1].initial or 0.0,
                'initial_amount': initial_line[:1].initial_amount or 0.0,
                'lines': lines,
            })
        return location_groups

    def _get_report_values(self, docids, data=None):
        wizard = self.env["imex.inventory.report.wizard"].browse(docids[0])
        details_model = self.env["imex.inventory.details.report"]
        details_model.init_results(wizard)
        details = details_model.search([], order="id")
        return {
            'doc_ids': docids,
            'doc_model': 'imex.inventory.report.wizard',
            'docs': wizard,
            'product_default_code': wizard.product_ids.default_code,
            'product_name': wizard.product_ids.name,
            'date_from': wizard.date_from or None,
            'date_to': wizard.date_to or fields.Date.context_today(self),
            'location': wizard.location_id.complete_name or None,
            'category': wizard.product_ids.categ_id.complete_name or None,
            'location_groups': self._group_details_by_location(details),
        }
