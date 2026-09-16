# -*- coding: utf-8 -*-
from odoo import api, models
from odoo.exceptions import ValidationError

from .location_helpers import loc_contained, build_line_mismatch_message


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    # A move line's source/destination must stay inside the subtree of the
    # matching move-header location. The FIFO valuation layer takes its
    # warehouse from the move header while physical stock follows the move
    # line, so a cross-warehouse divergence silently splits value from
    # quantity (POJ0012387).
    #
    # Containment, not equality: Odoo legitimately reserves / puts stock at
    # child locations of the header. Only a line landing *outside* the header
    # subtree - in practice a different warehouse - is acted on.
    #
    # Unbuild is designed to return components to several warehouses (one
    # produce move per component, buz_mrp_unbuild_enhancement). The operator
    # may set the destination on the raw move line before posting; for a
    # not-yet-done unbuild move the line is the source of truth, so the
    # header is realigned to it (keeping the valuation layer correct)
    # instead of blocking. Everything else is blocked.
    #
    # Implemented as create / write hooks (not @api.constrains) so it fires
    # only when the *line's own* location is set, never on the recompute
    # cascade a move-header location change triggers. Bypass with context
    # `skip_location_consistency_check`.

    _LOCATION_KEYS = ("location_id", "location_dest_id", "move_id")

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines._check_line_within_move_header()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if any(k in vals for k in self._LOCATION_KEYS):
            self._check_line_within_move_header()
        return res

    @staticmethod
    def _bad_axes(line, move):
        axes = []
        if not loc_contained(line.location_id, move.location_id):
            axes.append("source")
        if not loc_contained(line.location_dest_id, move.location_dest_id):
            axes.append("dest")
        return axes

    def _is_unbuild_move(self, move):
        return bool(
            ("unbuild_id" in move._fields and move.unbuild_id)
            or ("consume_unbuild_id" in move._fields and move.consume_unbuild_id))

    def _realign_unbuild_header(self, move, axes):
        """Point the move header at its lines' actual location(s), for a
        not-yet-done unbuild move. Returns True only if every bad axis is
        resolved (all the move's non-zero lines agree on one location for
        that axis); otherwise the caller blocks."""
        # `self` (the line that triggered the check) may not be in
        # move.move_line_ids yet on the create path.
        lines = move.move_line_ids | self
        vals = {}
        for axis in axes:
            field = "location_id" if axis == "source" else "location_dest_id"
            locs = lines.filtered(
                lambda l: l.quantity or l.quantity_product_uom).mapped(field)
            if len(locs) != 1:
                return False
            vals[field] = locs.id
            if axis == "dest" and "warehouse_id" in move._fields:
                vals["warehouse_id"] = locs.warehouse_id.id or False
        if not vals:
            return False
        reserved = move.state in ("assigned", "partially_available") \
            and bool(move.move_line_ids)
        if reserved:
            move._do_unreserve()
        move.with_context(skip_location_consistency_check=True).write(vals)
        if reserved:
            move._action_assign()
        return True

    def _check_line_within_move_header(self):
        if self.env.context.get("skip_location_consistency_check"):
            return
        for line in self:
            move = line.move_id
            if not move:
                continue
            bad_axes = self._bad_axes(line, move)
            if not bad_axes:
                continue
            if (self._is_unbuild_move(move) and move.state != "done"
                    and line._realign_unbuild_header(move, bad_axes)):
                continue
            raise ValidationError(
                build_line_mismatch_message(line, bad_axes))
