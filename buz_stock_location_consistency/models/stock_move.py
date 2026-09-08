# -*- coding: utf-8 -*-
from odoo import api, models, _
from odoo.exceptions import ValidationError

from .location_helpers import loc_contained, build_mismatch_message


class StockMove(models.Model):
    _inherit = "stock.move"

    def _consistency_out_of_subtree_lines(self, parent_loc):
        """move lines of self whose source is outside parent_loc's subtree."""
        return self.move_line_ids.filtered(
            lambda l: not loc_contained(l.location_id, parent_loc))

    def write(self, vals):
        if "location_id" not in vals or self.env.context.get(
                "skip_location_consistency_check"):
            return super().write(vals)

        new_loc = self.env["stock.location"].browse(vals["location_id"])
        to_reassign = self.env["stock.move"]

        for move in self:
            if move.location_id.id == new_loc.id:
                continue

            already_bad = bool(move._consistency_out_of_subtree_lines(move.location_id))
            would_be_bad = move._consistency_out_of_subtree_lines(new_loc)

            if move.state == "done":
                if would_be_bad and not already_bad:
                    raise ValidationError(
                        build_mismatch_message(move, would_be_bad, new_loc))
                continue

            if move.state in ("assigned", "partially_available") and move.move_line_ids:
                move._do_unreserve()
                to_reassign |= move

        res = super().write(vals)

        # re-point unreserved lines that are now out of subtree
        for move in self:
            if move.state in ("draft", "confirmed", "waiting") and move.move_line_ids:
                stale = move._consistency_out_of_subtree_lines(move.location_id)
                if stale:
                    stale.with_context(
                        skip_location_consistency_check=True
                    ).write({"location_id": move.location_id.id})

        if to_reassign:
            to_reassign._action_assign()
            for move in to_reassign:
                if move.state not in ("assigned", "done"):
                    move.picking_id.message_post(body=_(
                        "ตำแหน่งต้นทางถูกเปลี่ยน แต่ระบบจองสินค้าที่ตำแหน่งใหม่ไม่พอ "
                        "(move %(name)s กลับเป็นสถานะ %(state)s)",
                    ) % {"name": move.display_name, "state": move.state})
        return res

    @api.constrains("location_id")
    def _check_move_line_location_containment(self):
        if self.env.context.get("skip_location_consistency_check"):
            return
        for move in self:
            if move.state != "done":
                continue
            bad = move._consistency_out_of_subtree_lines(move.location_id)
            if bad:
                raise ValidationError(
                    build_mismatch_message(move, bad, move.location_id))
