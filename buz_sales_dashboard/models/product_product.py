from odoo import fields, models


class ProductProduct(models.Model):
    _inherit = "product.product"

    exclude_from_sales_dashboard = fields.Boolean(
        string="ไม่นับยอดใน Sales Dashboard",
        help="บรรทัดของสินค้านี้ (เช่น เงินมัดจำ ค่าธรรมเนียมรูดบัตร) "
             "จะไม่ถูกนับในทุกคอลัมน์ของ Sales Dashboard",
    )
