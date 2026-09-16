# -*- coding: utf-8 -*-
from odoo import fields, models


class BuzStockLocationMismatchClearance(models.Model):
    """One row per move whose header/line location mismatch has been
    resolved (or accepted). The mismatch report LEFT JOINs this table to
    show a `cleared` flag, who cleared it and when, so a worked backlog
    row drops out of the default "Open" filter instead of lingering.
    """
    _name = "buz.stock.location.mismatch.clearance"
    _description = "Location Mismatch Clearance"
    _rec_name = "move_id"

    move_id = fields.Many2one(
        "stock.move", required=True, ondelete="cascade", index=True)
    user_id = fields.Many2one(
        "res.users", string="Cleared By",
        default=lambda self: self.env.user, required=True)
    date = fields.Datetime(
        string="Cleared On", default=fields.Datetime.now, required=True)
    note = fields.Char(string="Resolution Note")

    _sql_constraints = [
        ("move_uniq", "unique(move_id)",
         "This move's location mismatch is already cleared."),
    ]
