from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    exclude_from_margin = fields.Boolean(
        string="ไม่คำนวณ Margin",
        default=False,
        help="เมื่อติ๊กถูก ระบบจะไม่นำสินค้านี้ไปคำนวณ Margin ใน Sale Order "
             "(เช่น ค่าขนส่ง, ค่าบริการ)"
    )
