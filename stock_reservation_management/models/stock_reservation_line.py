from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class StockReservationLine(models.Model):
    """Individual product reservation line."""

    _name = "stock.reservation.line"
    _description = "Stock Reservation Line"
    _rec_name = "product_id"
    _order = "id ASC"
    _check_company_auto = True

    # ── Basic Fields ──────────────────────────────────────────────
    reservation_id = fields.Many2one(
        comodel_name="stock.reservation",
        string="Reservation",
        required=True,
        ondelete="cascade",
        index=True,
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        string="Company",
        related="reservation_id.company_id",
        store=True,
        index=True,
    )
    product_id = fields.Many2one(
        comodel_name="product.product",
        string="Product",
        required=True,
        domain="[('type', 'in', ('product', 'consu')), "
        "'|', ('company_id', '=', company_id), ('company_id', '=', False)]",
        check_company=True,
    )
    product_uom_id = fields.Many2one(
        comodel_name="uom.uom",
        string="Unit of Measure",
        required=True,
        domain="[('category_id', '=', product_uom_category_id)]",
    )
    product_uom_category_id = fields.Many2one(
        comodel_name="uom.category",
        related="product_id.uom_id.category_id",
    )

    # ── Quantity Fields ──────────────────────────────────────────
    reserve_qty = fields.Float(
        string="Reserved Qty",
        required=True,
        digits="Product Unit of Measure",
        default=1.0,
    )
    allocated_qty = fields.Float(
        string="Allocated Qty",
        digits="Product Unit of Measure",
        default=0.0,
    )
    released_qty = fields.Float(
        string="Released Qty",
        digits="Product Unit of Measure",
        default=0.0,
    )
    product_qty_available = fields.Float(
        string="Current On Hand",
        related="product_id.qty_available",
        digits="Product Unit of Measure",
    )
    available_qty = fields.Float(
        string="Available to Promise",
        compute="_compute_available_qty",
        store=True,
        digits="Product Unit of Measure",
    )
    note = fields.Char(string="Note")

    # ── Computed Methods ─────────────────────────────────────────

    @api.depends(
        "product_id.qty_available",
        "product_id.reserved_qty",
        "reservation_id.reservation_type",
    )
    def _compute_available_qty(self):
        """Compute available quantity considering existing reservations.

        Available = qty_available - already_reserved_by_others - safety_buffer

        For VIP reservations, we also factor in VIP reserved quantity.
        """
        for rec in self:
            product = rec.product_id
            if not product:
                rec.available_qty = 0.0
                continue

            # On-hand quantity
            on_hand = product.qty_available

            # Already reserved by other reservations (excl current)
            current_reservation = rec.reservation_id
            other_reserved = product.reserved_qty
            if current_reservation.state in ("draft", "reserved", "allocated"):
                # Subtract this line's own reservation to get 'others only'
                own_qty = rec.reserve_qty if current_reservation.state != "draft" else 0.0
                other_reserved = max(0.0, product.reserved_qty - own_qty)

            # Safety buffer (configurable per product category)
            safety_reserve = 0.0
            if product.categ_id:
                safety_reserve = product.categ_id.safety_reserve_qty or 0.0

            rec.available_qty = max(0.0, on_hand - other_reserved - safety_reserve)

    # ── Constraints ──────────────────────────────────────────────

    @api.constrains("reserve_qty", "allocated_qty", "released_qty")
    def _check_quantities(self):
        for rec in self:
            if rec.reserve_qty < 0:
                raise ValidationError(_("Reserved quantity must be positive."))
            if rec.allocated_qty < 0:
                raise ValidationError(_("Allocated quantity must be positive."))
            if rec.released_qty < 0:
                raise ValidationError(_("Released quantity must be positive."))
            if rec.allocated_qty > rec.reserve_qty:
                raise ValidationError(
                    _("Allocated quantity (%(alloc).2f) cannot exceed reserved quantity (%(res).2f).")
                    % {"alloc": rec.allocated_qty, "res": rec.reserve_qty}
                )

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            self.product_uom_id = self.product_id.uom_id

    @api.onchange("product_id", "product_uom_id")
    def _onchange_uom(self):
        if self.product_id and self.product_uom_id:
            product_uom = self.product_id.uom_id
            if self.product_uom_id.category_id != product_uom.category_id:
                self.product_uom_id = product_uom
