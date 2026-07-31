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
        if line._has_non_draft_bill():
            raise UserError(
                "บรรทัดนี้มีบิลที่ยืนยันแล้ว (posted/cancel) "
                "ไม่สามารถแก้ไขรหัสสินค้าได้ บิลต้องเป็น draft เท่านั้น"
            )

        old_name = line.product_id.display_name
        new_product = self.new_product_id
        line.write({
            "product_id": new_product.id,
            "name": new_product.display_name,
        })
        # ponytail: sync draft bill lines so PO and bill stay consistent
        draft_move_lines = line.invoice_lines.filtered(
            lambda ml: ml.move_id.state == "draft"
        )
        if draft_move_lines:
            draft_move_lines.write({
                "product_id": new_product.id,
                "name": new_product.display_name,
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
