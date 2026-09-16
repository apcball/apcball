# -*- coding: utf-8 -*-
import logging

from odoo import api, models, _
from odoo.exceptions import ValidationError

from .location_helpers import loc_contained, build_mismatch_message

_logger = logging.getLogger(__name__)

# (vals key, human axis) for the two move-header location axes we guard.
_AXES = (("location_id", "source"), ("location_dest_id", "dest"))


class StockMove(models.Model):
    _inherit = "stock.move"

    def _consistency_out_of_subtree_lines(self, parent_loc, axis="source"):
        """move lines of self whose location on `axis` is outside
        parent_loc's subtree. axis is "source" (line.location_id) or
        "dest" (line.location_dest_id)."""
        field = "location_id" if axis == "source" else "location_dest_id"
        return self.move_line_ids.filtered(
            lambda l: not loc_contained(l[field], parent_loc))

    def write(self, vals):
        touched = [(k, ax) for (k, ax) in _AXES if k in vals]
        if not touched or self.env.context.get(
                "skip_location_consistency_check"):
            return super().write(vals)

        to_reassign = self.env["stock.move"]

        for move in self:
            for vals_key, axis in touched:
                new_loc = self.env["stock.location"].browse(vals[vals_key])
                cur_loc = move.location_id if axis == "source" \
                    else move.location_dest_id
                if cur_loc.id == new_loc.id:
                    continue

                already_bad = bool(
                    move._consistency_out_of_subtree_lines(cur_loc, axis))
                would_be_bad = move._consistency_out_of_subtree_lines(
                    new_loc, axis)

                if move.state == "done":
                    if would_be_bad and not already_bad:
                        raise ValidationError(build_mismatch_message(
                            move, would_be_bad, new_loc))
                    continue

                # Only a source change invalidates the reservation; unreserve
                # now and reassign after the header moves. A dest change does
                # not touch reserved quants.
                if (axis == "source"
                        and move.state in ("assigned", "partially_available")
                        and move.move_line_ids):
                    move._do_unreserve()
                    to_reassign |= move

        res = super().write(vals)

        # re-point unreserved / unreserved-state lines now outside the new
        # header subtree (nothing reserved, so a direct write is safe).
        for move in self:
            if move.state not in ("draft", "confirmed", "waiting"):
                continue
            if not move.move_line_ids:
                continue
            for _vk, axis in touched:
                parent = move.location_id if axis == "source" \
                    else move.location_dest_id
                stale = move._consistency_out_of_subtree_lines(parent, axis)
                if stale:
                    field = "location_id" if axis == "source" \
                        else "location_dest_id"
                    stale.with_context(
                        skip_location_consistency_check=True
                    ).write({field: parent.id})

        if to_reassign:
            to_reassign._action_assign()
            for move in to_reassign:
                if move.state in ("assigned", "done"):
                    continue
                msg = _(
                    "ตำแหน่งต้นทางถูกเปลี่ยน แต่ระบบจองสินค้าที่ตำแหน่งใหม่ไม่พอ "
                    "(move %(name)s กลับเป็นสถานะ %(state)s)",
                ) % {"name": move.display_name, "state": move.state}
                if move.picking_id:
                    move.picking_id.message_post(body=msg)
                else:
                    _logger.warning("buz_stock_location_consistency: %s", msg)
        return res

    @api.constrains("location_id", "location_dest_id")
    def _check_move_line_location_containment(self):
        """Backstop for ORM paths that change a done move's header location
        without going through write() above. Delegates to the move-line
        check so the message and containment rule stay in one place."""
        if self.env.context.get("skip_location_consistency_check"):
            return
        for move in self:
            if move.state != "done":
                continue
            move.move_line_ids._check_line_within_move_header()
