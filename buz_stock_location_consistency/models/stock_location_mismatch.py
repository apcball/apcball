# -*- coding: utf-8 -*-
from odoo import fields, models, tools

# Only surface mismatches whose effective (movement) date is on or after this
# wall-clock instant in MISMATCH_TZ. Older documents are stale backlog and are
# excluded from the report entirely. stock_move.date / stock_move_line.date are
# stored as naive UTC timestamps, so the SQL converts this cutoff to UTC.
MISMATCH_EFFECTIVE_CUTOFF = "2025-03-31 00:00:00"
MISMATCH_TZ = "Asia/Bangkok"


class BuzStockLocationMismatch(models.Model):
    _name = "buz.stock.location.mismatch"
    _description = "Stock Move Line / Header Location Mismatch"
    _auto = False
    _order = "effective_date desc"

    picking_id = fields.Many2one("stock.picking", readonly=True)
    move_id = fields.Many2one("stock.move", readonly=True)
    product_id = fields.Many2one("product.product", readonly=True)
    ml_location_id = fields.Many2one("stock.location", string="Move Line Source", readonly=True)
    header_location_id = fields.Many2one("stock.location", string="Header Source", readonly=True)
    ml_location_dest_id = fields.Many2one("stock.location", string="Move Line Dest", readonly=True)
    header_location_dest_id = fields.Many2one("stock.location", string="Header Dest", readonly=True)
    quantity = fields.Float(readonly=True)
    state = fields.Char(readonly=True)
    move_write_uid = fields.Many2one("res.users", string="Header Last Edited By", readonly=True)
    move_write_date = fields.Datetime(string="Header Last Edited", readonly=True)
    effective_date = fields.Datetime(
        string="Effective Date", readonly=True,
        help="When the stock movement took effect (move done date), "
             "not the last edit time.")
    picking_type_id = fields.Many2one("stock.picking.type", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

    axis = fields.Char(readonly=True, help="Which location axis diverges: source / dest / source+dest")
    cross_warehouse = fields.Boolean(
        readonly=True,
        string="Cross-warehouse",
        help="True when a diverging line lands in a different warehouse than "
             "the header - the case that desyncs FIFO valuation (keyed on the "
             "header warehouse) from physical stock. False = a header/line "
             "split within one warehouse's sub-locations (no valuation impact).")

    clearance_id = fields.Many2one(
        "buz.stock.location.mismatch.clearance", readonly=True)
    cleared = fields.Boolean(readonly=True, string="Cleared")
    cleared_by = fields.Many2one("res.users", readonly=True, string="Cleared By")
    cleared_date = fields.Datetime(readonly=True, string="Cleared On")
    clearance_note = fields.Char(readonly=True, string="Resolution Note")

    def action_mark_cleared(self):
        """Tag every selected row's move as resolved. Idempotent."""
        Clr = self.env["buz.stock.location.mismatch.clearance"]
        for move in self.mapped("move_id"):
            if move and not Clr.search_count([("move_id", "=", move.id)]):
                Clr.create({"move_id": move.id})
        return True

    def action_reopen(self):
        self.env["buz.stock.location.mismatch.clearance"].search(
            [("move_id", "in", self.mapped("move_id").ids)]).unlink()
        return True

    def init(self):
        tools.drop_view_if_exists(self.env.cr, self._table)
        self.env.cr.execute("""
            CREATE VIEW buz_stock_location_mismatch AS (
                SELECT ml.id                  AS id,
                       ml.picking_id          AS picking_id,
                       ml.move_id             AS move_id,
                       ml.product_id          AS product_id,
                       ml.location_id         AS ml_location_id,
                       m.location_id          AS header_location_id,
                       ml.location_dest_id    AS ml_location_dest_id,
                       m.location_dest_id     AS header_location_dest_id,
                       ml.quantity            AS quantity,
                       m.state                AS state,
                       m.write_uid            AS move_write_uid,
                       m.write_date           AS move_write_date,
                       COALESCE(ml.date, m.date) AS effective_date,
                       p.picking_type_id      AS picking_type_id,
                       m.company_id           AS company_id,
                       trim(BOTH '+' FROM
                            CASE WHEN src.bad THEN 'source+' ELSE '' END ||
                            CASE WHEN dst.bad THEN 'dest' ELSE '' END) AS axis,
                       COALESCE(
                          (src.bad AND mls.warehouse_id IS DISTINCT FROM lm_src.warehouse_id)
                          OR (dst.bad AND mld.warehouse_id IS DISTINCT FROM lm_dst.warehouse_id),
                          false) AS cross_warehouse,
                       clr.id                 AS clearance_id,
                       (clr.id IS NOT NULL)   AS cleared,
                       clr.user_id            AS cleared_by,
                       clr.date               AS cleared_date,
                       clr.note               AS clearance_note
                FROM stock_move_line ml
                JOIN stock_move m           ON m.id = ml.move_id
                LEFT JOIN stock_picking p   ON p.id = ml.picking_id
                LEFT JOIN buz_stock_location_mismatch_clearance clr ON clr.move_id = m.id
                JOIN stock_location lm_src  ON lm_src.id = m.location_id
                JOIN stock_location lm_dst  ON lm_dst.id = m.location_dest_id
                LEFT JOIN stock_location mls ON mls.id = ml.location_id
                LEFT JOIN stock_location mld ON mld.id = ml.location_dest_id
                LEFT JOIN LATERAL (
                    SELECT (ml.location_id <> m.location_id
                            AND NOT EXISTS (
                                SELECT 1 FROM stock_location s
                                WHERE s.id = ml.location_id
                                  AND s.parent_path LIKE lm_src.parent_path || '%%'
                            )) AS bad
                ) src ON true
                LEFT JOIN LATERAL (
                    SELECT (ml.location_dest_id <> m.location_dest_id
                            AND NOT EXISTS (
                                SELECT 1 FROM stock_location s
                                WHERE s.id = ml.location_dest_id
                                  AND s.parent_path LIKE lm_dst.parent_path || '%%'
                            )) AS bad
                ) dst ON true
                WHERE m.state IN ('done', 'assigned', 'partially_available')
                  AND (src.bad OR dst.bad)
                  AND COALESCE(ml.date, m.date)
                      >= (TIMESTAMP %s AT TIME ZONE %s AT TIME ZONE 'UTC')
            )
        """, (MISMATCH_EFFECTIVE_CUTOFF, MISMATCH_TZ))
