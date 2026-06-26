import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """Extend sale.order with reservation integration."""

    _inherit = "sale.order"

    # ── Reservation Fields ───────────────────────────────────────
    reservation_ids = fields.One2many(
        comodel_name="stock.reservation",
        inverse_name="sale_order_id",
        string="Reservations",
        domain=[("state", "not in", ("cancel",))],
    )
    reservation_count = fields.Integer(
        string="Reservation Count",
        compute="_compute_reservation_count",
        store=True,
    )
    reservation_state = fields.Selection(
        selection=[
            ("no", "No Reservation"),
            ("draft", "Draft"),
            ("partial", "Partially Reserved"),
            ("reserved", "Fully Reserved"),
            ("allocated", "Allocated"),
            ("delivered", "Delivered"),
        ],
        string="Reservation Status",
        compute="_compute_reservation_state",
        store=True,
    )

    # ── Computed Methods ─────────────────────────────────────────

    @api.depends("reservation_ids")
    def _compute_reservation_count(self):
        for order in self:
            order.reservation_count = len(order.reservation_ids)

    @api.depends("reservation_ids.state", "reservation_ids.line_ids.reserve_qty",
                 "order_line.product_uom_qty")
    def _compute_reservation_state(self):
        for order in self:
            if not order.reservation_ids:
                order.reservation_state = "no"
                continue

            states = order.reservation_ids.mapped("state")

            if all(s == "delivered" for s in states):
                order.reservation_state = "delivered"
            elif all(s == "allocated" for s in states):
                order.reservation_state = "allocated"
            elif all(s in ("reserved", "allocated", "delivered") for s in states):
                # Check if fully reserved
                total_order_qty = sum(order.order_line.mapped("product_uom_qty"))
                total_reserved_qty = sum(
                    order.reservation_ids.filtered(
                        lambda r: r.state in ("reserved", "allocated", "delivered")
                    ).mapped("total_reserve_qty")
                )
                if total_reserved_qty >= total_order_qty:
                    order.reservation_state = "reserved"
                elif total_reserved_qty > 0:
                    order.reservation_state = "partial"
                else:
                    order.reservation_state = "draft"
            elif any(s in ("draft", "waiting_approval") for s in states):
                order.reservation_state = "draft"
            else:
                order.reservation_state = "no"

    # ── Action Methods ───────────────────────────────────────────

    def action_create_reservation(self):
        """Create a reservation from sale order lines."""
        self.ensure_one()
        if not self.order_line:
            raise UserError(_("Cannot create a reservation for an empty sales order."))

        # Check for existing reservations
        existing = self.reservation_ids.filtered(lambda r: r.state in ("draft", "reserved", "allocated"))
        if existing:
            raise UserError(
                _("This sales order already has an active reservation (%s). "
                  "Please release or cancel it first.") % existing[0].name
            )

        # Determine reservation type based on customer
        res_type = "vip" if self.partner_id.is_vip_customer else "sale"

        reservation = self.env["stock.reservation"].create(
            {
                "customer_id": self.partner_id.id,
                "sale_order_id": self.id,
                "reservation_type": res_type,
                "priority": self._get_reservation_priority(),
                "warehouse_id": self.warehouse_id.id or self.env.user._get_default_warehouse_id(),
                "user_id": self.user_id.id or self.env.user.id,
                "line_ids": [
                    (
                        0,
                        0,
                        {
                            "product_id": line.product_id.id,
                            "product_uom_id": line.product_uom_id.id,
                            "reserve_qty": line.product_uom_qty,
                        },
                    )
                    for line in self.order_line
                    if line.product_id.type in ("product", "consu")
                ],
            }
        )

        # If automatically reserve after confirmation
        if self.state in ("sale", "done"):
            reservation.action_reserve()

        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.reservation",
            "res_id": reservation.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_reservations(self):
        """View reservations linked to this order."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock_reservation_management.action_stock_reservation"
        )
        action["domain"] = [("sale_order_id", "=", self.id)]
        action["context"] = {
            "default_customer_id": self.partner_id.id,
            "default_sale_order_id": self.id,
            "default_warehouse_id": self.warehouse_id.id or self.env.user._get_default_warehouse_id(),
        }
        return action

    def action_release_reservation(self):
        """Release all reservations linked to this order."""
        self.ensure_one()
        active = self.reservation_ids.filtered(
            lambda r: r.state not in ("released", "cancel", "delivered", "expired")
        )
        if not active:
            raise UserError(_("No active reservations to release."))
        active.action_release()
        return True

    # ── Helper Methods ───────────────────────────────────────────

    def _get_reservation_priority(self):
        """Determine priority based on customer/order context."""
        self.ensure_one()
        if self.partner_id.is_vip_customer:
            return "vip"
        if self.priority and self.priority in ("very_high", "high"):
            return "critical"
        return "normal"

    # ── Overrides ───────────────────────────────────────────────

    def action_confirm(self):
        """Automatically create reservation on confirmation if configured."""
        result = super().action_confirm()
        for order in self:
            if order.reservation_count == 0 and order.order_line:
                try:
                    reservation = self.env["stock.reservation"].create(
                        {
                            "customer_id": order.partner_id.id,
                            "sale_order_id": order.id,
                            "reservation_type": "vip" if order.partner_id.is_vip_customer else "sale",
                            "priority": order._get_reservation_priority(),
                            "warehouse_id": order.warehouse_id.id
                            or order.env.user._get_default_warehouse_id(),
                            "user_id": order.user_id.id or order.env.user.id,
                            "line_ids": [
                                (
                                    0,
                                    0,
                                    {
                                        "product_id": line.product_id.id,
                                        "product_uom_id": line.product_uom_id.id,
                                        "reserve_qty": line.product_uom_qty,
                                    },
                                )
                                for line in order.order_line
                                if line.product_id.type in ("product", "consu")
                            ],
                        }
                    )
                    reservation.action_reserve()
                except Exception as e:
                    _logger.warning(
                        "Could not auto-create reservation for SO %s: %s", order.name, str(e)
                    )
        return result
