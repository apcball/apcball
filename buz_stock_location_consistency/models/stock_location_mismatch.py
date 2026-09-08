# -*- coding: utf-8 -*-
from odoo import fields, models, tools


class BuzStockLocationMismatch(models.Model):
    _name = "buz.stock.location.mismatch"
    _description = "Stock Move Line / Header Location Mismatch"
    _auto = False
    _order = "move_write_date desc"

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
    picking_type_id = fields.Many2one("stock.picking.type", readonly=True)
    company_id = fields.Many2one("res.company", readonly=True)

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
                       p.picking_type_id      AS picking_type_id,
                       m.company_id           AS company_id
                FROM stock_move_line ml
                JOIN stock_move m           ON m.id = ml.move_id
                LEFT JOIN stock_picking p   ON p.id = ml.picking_id
                JOIN stock_location lm      ON lm.id = m.location_id
                LEFT JOIN stock_location ls
                       ON ls.id = ml.location_id
                      AND ls.parent_path LIKE lm.parent_path || '%%'
                WHERE m.state IN ('done', 'assigned', 'partially_available')
                  AND ml.location_id <> m.location_id
                  AND ls.id IS NULL
            )
        """)
