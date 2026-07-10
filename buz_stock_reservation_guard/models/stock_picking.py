from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockPicking(models.Model):
    _inherit = "stock.picking"

    bypass_reservation_guard = fields.Boolean(
        default=False,
        help="Bypass stock reservation guard checks for this picking.",
    )

    def action_assign(self):
        self._check_exact_source_availability_for_assignment()
        return super().action_assign()

    def button_validate(self):
        self._check_exact_source_availability_for_validation()
        return super().button_validate()

    def force_unreserve(self):
        self.write({"bypass_reservation_guard": True})
        return self.button_validate()

    def _check_exact_source_availability_for_assignment(self):
        errors = []
        for picking in self.filtered(
            lambda p: p.picking_type_code in ("internal", "outgoing")
            and p.state not in ("done", "cancel")
            and not p.bypass_reservation_guard
        ):
            for move in picking.move_ids.filtered(
                lambda m: m.state not in ("done", "cancel")
                and m.product_id.type == "product"
                and m.location_id.usage in ("internal", "transit")
                and not m._should_bypass_reservation()
            ):
                available_qty = self.env["stock.quant"]._get_available_quantity(
                    move.product_id,
                    move.location_id,
                    strict=True,
                )
                if float_compare(
                    available_qty,
                    0.0,
                    precision_rounding=move.product_uom.rounding,
                ) <= 0:
                    errors.append(
                        _(
                            "%(picking)s: %(product)s ที่ %(location)s "
                            "(ไม่มีสินค้าคงเหลือ)"
                        )
                        % {
                            "picking": picking.name,
                            "product": move.product_id.display_name,
                            "location": move.location_id.complete_name,
                        }
                    )
        if errors:
            raise UserError(
                _("ไม่สามารถจองสินค้าได้ เนื่องจาก location ต้นทางไม่มีสินค้า:\n%s")
                % "\n".join(errors)
            )

    def _get_move_reserved_qty(self, move):
        if "reserved_availability" in move._fields:
            return move.reserved_availability
        return sum(
            move.move_line_ids.filtered(lambda ml: ml.state != "cancel").mapped("quantity")
        )

    def _check_exact_source_availability_for_validation(self):
        errors = []
        for picking in self.filtered(
            lambda p: p.picking_type_code in ("internal", "outgoing")
            and p.state not in ("done", "cancel")
            and not p.bypass_reservation_guard
        ):
            demand_map = {}
            for move_line in picking.move_line_ids.filtered(
                lambda ml: ml.product_id.type == "product"
                and ml.location_id.usage in ("internal", "transit")
                and ml.quantity > 0
                and ml.state != "cancel"
            ):
                key = (
                    move_line.product_id.id,
                    move_line.location_id.id,
                    move_line.lot_id.id,
                    move_line.package_id.id,
                    move_line.owner_id.id,
                )
                demand_map.setdefault(
                    key,
                    {
                        "product": move_line.product_id,
                        "location": move_line.location_id,
                        "lot": move_line.lot_id,
                        "package": move_line.package_id,
                        "owner": move_line.owner_id,
                        "quantity": 0.0,
                    },
                )
                demand_map[key]["quantity"] += move_line.quantity

            if not demand_map:
                for move in picking.move_ids.filtered(
                    lambda m: m.state not in ("done", "cancel")
                    and m.product_id.type == "product"
                    and m.location_id.usage in ("internal", "transit")
                ):
                    key = (
                        move.product_id.id,
                        move.location_id.id,
                        False,
                        False,
                        False,
                    )
                    demand_map.setdefault(
                        key,
                        {
                            "product": move.product_id,
                            "location": move.location_id,
                            "lot": self.env["stock.lot"],
                            "package": self.env["stock.quant.package"],
                            "owner": self.env["res.partner"],
                            "quantity": 0.0,
                        },
                    )
                    demand_map[key]["quantity"] += move.quantity or move.product_uom_qty

            for values in demand_map.values():
                available_qty = self.env["stock.quant"]._get_available_quantity(
                    values["product"],
                    values["location"],
                    lot_id=values["lot"],
                    package_id=values["package"],
                    owner_id=values["owner"],
                    strict=True,
                )
                if float_compare(
                    available_qty,
                    0.0,
                    precision_rounding=values["product"].uom_id.rounding,
                ) <= 0:
                    errors.append(
                        _(
                            "%(picking)s: %(product)s ที่ %(location)s "
                            "(ไม่มีสินค้าคงเหลือ)"
                        )
                        % {
                            "picking": picking.name,
                            "product": values["product"].display_name,
                            "location": values["location"].complete_name,
                        }
                    )

        if errors:
            raise UserError(
                _("ไม่สามารถตรวจรับ/โอนย้ายสินค้าได้ เนื่องจาก location ต้นทางไม่มีสินค้า:\n%s")
                % "\n".join(errors)
            )
