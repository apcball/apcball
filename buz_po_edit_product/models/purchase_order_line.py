from odoo import fields, models


class PurchaseOrderLine(models.Model):
    _inherit = "purchase.order.line"

    allow_product_edit = fields.Boolean(
        string="Can Edit Product",
        compute="_compute_allow_product_edit",
    )

    def _compute_allow_product_edit(self):
        for line in self:
            line.allow_product_edit = (
                line.order_id.state in ("purchase", "done")
                and not line.qty_received
                and not line.qty_invoiced
            )

    def action_open_change_product_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "แก้ไขรหัสสินค้า (กรณี Return)",
            "res_model": "buz.po.line.change.product.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_line_id": self.id,
                "default_old_product_id": self.product_id.id,
            },
        }
