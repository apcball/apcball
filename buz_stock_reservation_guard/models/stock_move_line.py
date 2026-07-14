from odoo import _, api, models
from odoo.exceptions import UserError
from odoo.tools import float_compare


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            self._check_manual_reservation_availability(vals=vals)
        return super().create(vals_list)

    def write(self, vals):
        tracked_fields = {
            "product_id",
            "location_id",
            "lot_id",
            "package_id",
            "owner_id",
            "quantity",
            "move_id",
            "picking_id",
        }
        if tracked_fields.intersection(vals):
            for line in self:
                line._check_manual_reservation_availability(vals=vals)
        return super().write(vals)

    def _check_manual_reservation_availability(self, vals=None):
        vals = vals or {}
        for line in self if self else self.browse():
            target = line._reservation_guard_target(vals)
            if not target:
                continue
            available_qty = line._reservation_guard_available_qty(target)
            if float_compare(
                available_qty,
                target["quantity"],
                precision_rounding=target["rounding"],
            ) < 0:
                raise UserError(
                    _(
                        "Cannot reserve %(qty)s %(uom)s of %(product)s from %(location)s "
                        "because the exact source location only has %(available)s %(uom)s available."
                    )
                    % {
                        "qty": target["quantity"],
                        "uom": target["uom_name"],
                        "product": target["product"].display_name,
                        "location": target["location"].complete_name,
                        "available": available_qty,
                    }
                )
        if not self and vals:
            target = self._reservation_guard_target(vals)
            if target:
                available_qty = self._reservation_guard_available_qty(target)
                if float_compare(
                    available_qty,
                    target["quantity"],
                    precision_rounding=target["rounding"],
                ) < 0:
                    raise UserError(
                        _(
                            "Cannot reserve %(qty)s %(uom)s of %(product)s from %(location)s "
                            "because the exact source location only has %(available)s %(uom)s available."
                        )
                        % {
                            "qty": target["quantity"],
                            "uom": target["uom_name"],
                            "product": target["product"].display_name,
                            "location": target["location"].complete_name,
                            "available": available_qty,
                        }
                    )

    def _reservation_guard_target(self, vals):
        move = self.env["stock.move"].browse(vals.get("move_id")) if vals.get("move_id") else self.move_id
        picking = self.env["stock.picking"].browse(vals.get("picking_id")) if vals.get("picking_id") else self.picking_id

        product = self.env["product.product"].browse(vals.get("product_id")) if vals.get("product_id") else self.product_id
        if not product and move:
            product = move.product_id
        location = self.env["stock.location"].browse(vals.get("location_id")) if vals.get("location_id") else self.location_id
        if not location and move:
            location = move.location_id
        if not location and picking:
            location = picking.location_id

        if "quantity" in vals:
            quantity = vals.get("quantity") or 0.0
        else:
            quantity = self.quantity

        lot = self.env["stock.lot"].browse(vals.get("lot_id")) if vals.get("lot_id") else self.lot_id
        package = self.env["stock.quant.package"].browse(vals.get("package_id")) if vals.get("package_id") else self.package_id
        owner = self.env["res.partner"].browse(vals.get("owner_id")) if vals.get("owner_id") else self.owner_id

        if not product or not location or quantity <= 0:
            return None
        if product.type != "product":
            return None

        effective_move = move or self.move_id
        effective_picking = picking or self.picking_id
        if effective_move and effective_move.state in ("done", "cancel"):
            return None
        if self.state in ("done", "cancel"):
            return None
        if effective_move and effective_move._should_bypass_reservation():
            return None
        if location.usage not in ("internal", "transit"):
            return None
        if location.id in self.env.company.bypass_reservation_guard_location_ids.ids:
            return None
        if effective_picking and effective_picking.picking_type_code not in ("internal", "outgoing"):
            return None
        if effective_picking and effective_picking.bypass_reservation_guard:
            return None

        return {
            "product": product,
            "location": location,
            "lot": lot,
            "package": package,
            "owner": owner,
            "quantity": quantity,
            "rounding": product.uom_id.rounding,
            "uom_name": product.uom_id.name,
        }

    def _reservation_guard_available_qty(self, target):
        available_qty = self.env["stock.quant"]._get_available_quantity(
            target["product"],
            target["location"],
            lot_id=target["lot"],
            package_id=target["package"],
            owner_id=target["owner"],
            strict=True,
        )

        if not self:
            return available_qty

        same_characteristics = (
            self.product_id == target["product"]
            and self.location_id == target["location"]
            and self.lot_id == target["lot"]
            and self.package_id == target["package"]
            and self.owner_id == target["owner"]
        )
        if same_characteristics and self.state not in ("done", "cancel"):
            available_qty += self.quantity
        return available_qty
