from odoo import fields, models
from odoo.exceptions import UserError


class PoLineChangeProductWizard(models.TransientModel):
    _name = "buz.po.line.change.product.wizard"
    _description = "Change PO Line Product (After Full Return)"

    line_id = fields.Many2one(
        "purchase.order.line", required=True, ondelete="cascade"
    )
    old_product_id = fields.Many2one("product.product", readonly=True)
    new_product_id = fields.Many2one(
        "product.product", string="รหัสสินค้าใหม่", required=True,
        domain="[('purchase_ok', '=', True), ('id', '!=', old_product_id)]",
    )
    reason = fields.Char(string="เหตุผล", required=True)

    def action_confirm(self):
        self.ensure_one()
        line = self.line_id
        order = line.order_id

        if order.state not in ("purchase", "done"):
            raise UserError("แก้ไขได้เฉพาะ PO ที่ยืนยันแล้วเท่านั้น")
        if line.qty_received:
            raise UserError(
                "ยังมียอดรับสินค้าค้างอยู่ (qty_received != 0) "
                "ต้อง return สินค้าคืนให้ครบก่อนจึงแก้ไขรหัสสินค้าได้"
            )
        if line.qty_invoiced:
            raise UserError(
                "บรรทัดนี้มีการตั้งบิลแล้ว (qty_invoiced != 0) "
                "ไม่สามารถแก้ไขรหัสสินค้าได้เพราะจะกระทบบัญชี"
            )

        old_name = line.product_id.display_name
        line.write({
            "product_id": self.new_product_id.id,
            "name": self.new_product_id.display_name,
        })
        order.message_post(
            body=(
                f"แก้ไขรหัสสินค้าใน PO line จาก <b>{old_name}</b> "
                f"เป็น <b>{self.new_product_id.display_name}</b><br/>"
                f"เหตุผล: {self.reason}<br/>"
                f"โดย: {self.env.user.name}"
            )
        )
        return {"type": "ir.actions.act_window_close"}
