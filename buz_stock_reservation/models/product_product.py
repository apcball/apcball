from odoo import _, fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    buz_reserved_qty = fields.Float(
        string="Reserved (Reservations)",
        compute="_compute_buz_reserved_qty",
        help="Quantity still held by active stock reservations.",
    )
    buz_available_qty = fields.Float(
        string="Available After Reservations",
        compute="_compute_buz_reserved_qty",
    )

    def _compute_buz_reserved_qty(self):
        groups = self.env["buz.stock.reservation.line"].read_group(
            [
                ("product_id", "in", self.ids),
                ("state", "in", ("reserved", "partially_released")),
            ],
            ["remaining_qty:sum"],
            ["product_id"],
        )
        reserved_by_product = {
            g["product_id"][0]: g["remaining_qty"] for g in groups
        }
        for product in self:
            product.buz_reserved_qty = reserved_by_product.get(product.id, 0.0)
            product.buz_available_qty = (
                product.qty_available - product.buz_reserved_qty
            )

    def action_view_buz_reservations(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Reservations"),
            "res_model": "buz.stock.reservation.line",
            "view_mode": "tree",
            "domain": [
                ("product_id", "=", self.id),
                ("state", "in", ("reserved", "partially_released")),
            ],
        }
