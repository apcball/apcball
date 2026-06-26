from odoo import api, fields, models, _


class ProductProduct(models.Model):
    """Extend product.product with reservation-related fields."""

    _inherit = "product.product"

    # ── Reservation Relation ────────────────────────────────────
    stock_reservation_line_ids = fields.One2many(
        comodel_name="stock.reservation.line",
        inverse_name="product_id",
        string="Stock Reservation Lines",
    )

    # ── Reservation Fields ───────────────────────────────────────
    reserved_qty = fields.Float(
        string="Reserved Quantity",
        compute="_compute_reserved_qty",
        store=True,
        digits="Product Unit of Measure",
        help="Total quantity reserved via stock reservations.",
        group_operator="sum",
    )
    available_after_reserve = fields.Float(
        string="Available After Reserve",
        compute="_compute_available_after_reserve",
        store=True,
        digits="Product Unit of Measure",
        help="Quantity on hand minus total reserved quantity.",
        group_operator="sum",
    )
    reservation_count = fields.Integer(
        string="Reservation Count",
        compute="_compute_reservation_count",
        store=True,
        help="Number of active reservations for this product.",
    )
    vip_reserved_qty = fields.Float(
        string="VIP Reserved Quantity",
        compute="_compute_vip_reserved_qty",
        store=True,
        digits="Product Unit of Measure",
        help="Quantity reserved for VIP customers.",
        group_operator="sum",
    )

    # ── Computed Methods ─────────────────────────────────────────

    @api.depends("stock_reservation_line_ids.reserve_qty",
                 "stock_reservation_line_ids.reservation_id.state")
    def _compute_reserved_qty(self):
        """Compute total reserved quantity from active reservation lines."""
        for product in self:
            active_states = ("draft", "reserved", "allocated")
            lines = product.stock_reservation_line_ids.filtered(
                lambda l: l.reservation_id.state in active_states
            )
            product.reserved_qty = sum(lines.mapped("reserve_qty"))

    @api.depends("qty_available", "reserved_qty")
    def _compute_available_after_reserve(self):
        """Available = On Hand - Reserved - Safety Reserve."""
        for product in self:
            safety = product.categ_id.safety_reserve_qty or 0.0
            product.available_after_reserve = max(
                0.0, product.qty_available - product.reserved_qty - safety
            )

    @api.depends("stock_reservation_line_ids.reservation_id.state")
    def _compute_reservation_count(self):
        """Count active reservations for this product."""
        for product in self:
            active_states = ("draft", "reserved", "allocated")
            reservations = product.stock_reservation_line_ids.mapped("reservation_id").filtered(
                lambda r: r.state in active_states
            )
            product.reservation_count = len(reservations)

    @api.depends("stock_reservation_line_ids.reserve_qty",
                 "stock_reservation_line_ids.reservation_id.reservation_type",
                 "stock_reservation_line_ids.reservation_id.state")
    def _compute_vip_reserved_qty(self):
        """Compute VIP-only reserved quantity."""
        for product in self:
            lines = product.stock_reservation_line_ids.filtered(
                lambda l: l.reservation_id.reservation_type == "vip"
                and l.reservation_id.state in ("draft", "reserved", "allocated")
            )
            product.vip_reserved_qty = sum(lines.mapped("reserve_qty"))

    # ── Action Methods ───────────────────────────────────────────

    def action_view_reservations(self):
        """Smart button: open reservations for this product."""
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "stock_reservation_management.action_stock_reservation"
        )
        lines = self.stock_reservation_line_ids
        reservation_ids = lines.mapped("reservation_id").ids
        action["domain"] = [("id", "in", reservation_ids)]
        action["context"] = {
            "default_reservation_type": "sale",
        }
        return action
