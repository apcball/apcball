# -*- coding: utf-8 -*-
from odoo import models


class StockPicking(models.Model):
    _inherit = "stock.picking"

    def write(self, vals):
        if "location_id" not in vals or self.env.context.get(
                "skip_location_consistency_check"):
            return super().write(vals)

        new_loc_id = vals["location_id"]
        to_reassign = self.env["stock.move"]
        for picking in self:
            if picking.location_id.id == new_loc_id:
                continue
            moves = picking.move_ids.filtered(lambda m: not m.scrapped)
            reserved = moves.filtered(
                lambda m: m.state in ("assigned", "partially_available")
                and m.move_line_ids)
            if reserved:
                reserved._do_unreserve()
                to_reassign |= reserved

        # core propagates location_id to move_ids -> re-enters StockMove.write,
        # which raises for done moves that would become out-of-subtree.
        res = super().write(vals)

        if to_reassign:
            to_reassign._action_assign()
        return res
