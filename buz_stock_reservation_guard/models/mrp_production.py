from odoo import _, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    def button_mark_done(self):
        self._check_raw_material_reservation_availability()
        return super().button_mark_done()

    def _check_raw_material_reservation_availability(self):
        """stock.move.line's own guard (_check_manual_reservation_availability)
        never fires for raw-material consumption: these moves carry no
        stock.picking (they're tied via raw_material_production_id instead),
        and by the time their quantity is finalized in stock.move._action_done()
        the move is already 'done' - which is the guard's own bypass
        condition. Check physical availability here, before consumption.

        Checked against move.product_uom_qty (the full intended demand for
        the current qty_producing), not move_line_ids.quantity: when a
        component is only partially reservable, Odoo still creates a
        move-line for just the reservable slice (state 'partially_available')
        and only manifests the shortfall as consumption inside
        _action_done() itself - after the move is already 'done'. Checking
        the line quantity here would miss exactly the shortfall this guard
        exists to catch.
        """
        bypass_loc_ids = self.env.company.bypass_reservation_guard_location_ids.ids
        errors = []
        for production in self:
            demand_map = {}
            ratio = 1.0
            if (
                production.product_qty
                and 0 < production.qty_producing < production.product_qty
            ):
                ratio = production.qty_producing / production.product_qty
            moves = production.move_raw_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
                and m.product_id.type == "product"
                and m.location_id.usage in ("internal", "transit")
                and m.location_id.id not in bypass_loc_ids
                and not m._should_bypass_reservation()
            )
            for move in moves:
                key = (move.product_id.id, move.location_id.id)
                demand_map.setdefault(
                    key, {"product": move.product_id, "location": move.location_id, "quantity": 0.0}
                )
                if move.picked and move.quantity:
                    need = move.quantity
                else:
                    # Partial production: only the share being produced now
                    # is consumed; the rest moves to the backorder.
                    need = move.product_uom_qty * ratio
                qty = move.product_uom._compute_quantity(
                    need, move.product_id.uom_id
                )
                demand_map[key]["quantity"] += qty
                # Own reservation must not count against the MO itself.
                demand_map[key]["own_reserved"] = demand_map[key].get(
                    "own_reserved", 0.0
                ) + sum(
                    ml.product_uom_id._compute_quantity(
                        ml.quantity, move.product_id.uom_id
                    )
                    for ml in move.move_line_ids
                    if ml.location_id == move.location_id
                )

            for values in demand_map.values():
                available_qty = self.env["stock.quant"]._get_available_quantity(
                    values["product"],
                    values["location"],
                    strict=True,
                ) + values.get("own_reserved", 0.0)
                if float_compare(
                    available_qty,
                    values["quantity"],
                    precision_rounding=values["product"].uom_id.rounding,
                ) < 0:
                    errors.append(
                        _(
                            "%(mo)s: %(product)s ที่ %(location)s "
                            "(ต้องใช้ %(need)s %(uom)s, สินค้าจริงคงเหลือ %(available)s %(uom)s)"
                        )
                        % {
                            "mo": production.name,
                            "product": values["product"].display_name,
                            "location": values["location"].complete_name,
                            "need": values["quantity"],
                            "available": available_qty,
                            "uom": values["product"].uom_id.name,
                        }
                    )
        if errors:
            raise UserError(
                _(
                    "ไม่สามารถผลิตได้ เนื่องจาก location วัตถุดิบต้นทางมีสินค้าจริงไม่เพียงพอ:\n%s"
                )
                % "\n".join(errors)
            )
