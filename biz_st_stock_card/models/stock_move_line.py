# -*- coding: utf-8 -*-
"""ดัชนีสำหรับคิวรียอดยกมาของสต๊อกการ์ด

``stock.move.line.date`` ไม่มี index ใน Odoo 17 (มีแต่ ``stock.move.date``) แต่
คิวรียอดยกมาต้องกวาดทุกบรรทัดที่ ``date < date_from`` ถ้าไม่มีดัชนีตัวนี้จะกลาย
เป็น seq scan ทั้งตาราง ซึ่งบน DB จริงคือหลายวินาทีต่อการเปิดรายงานหนึ่งครั้ง
"""

from odoo import models, tools


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def init(self):
        # partial index — รายงานสนใจเฉพาะบรรทัดที่ done เท่านั้น ดัชนีจึงเล็กกว่ามาก
        tools.create_index(
            self._cr,
            "stock_move_line_stock_card_idx",
            self._table,
            ["company_id", "product_id", "date"],
            where="state = 'done'",
        )
