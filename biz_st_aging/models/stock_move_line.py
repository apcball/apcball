# -*- coding: utf-8 -*-
"""ดัชนีสำหรับคิวรีประวัติทั้งหมดของรายงานอายุสินค้า

``stock.move.line.date`` ไม่มี index ใน Odoo 17 แต่รายงานต้องกวาดทุกบรรทัด done
ที่ ``date <= ณ วันที่`` (ยอดคงเหลือ, วันจ่ายล่าสุด, ชั้นรับเข้า) ถ้าไม่มีดัชนีจะเป็น
seq scan ทั้งตาราง

สองดัชนี partial (``WHERE state = 'done'``) คนละหน้าที่:

* ``(company_id, product_id, date)`` — คิวรีที่กรองสินค้า (FIFO walk, drill-down, stock card)
  ``biz_st_stock_card`` สร้างไว้แล้วในชื่อ ``stock_move_line_stock_card_idx`` ถ้ามีก็ใช้ร่วมกัน
* ``(company_id, date)`` — คิวรีบัญชีคุม opening/period/usage ที่กรองแค่บริษัท + ช่วงวันที่
  ดัชนีแรกช่วยไม่ได้เพราะ ``date`` อยู่คอลัมน์ที่สาม planner ใช้ได้แค่ prefix ``company_id``
  แล้วต้องไล่ทั้งบริษัท
"""

from odoo import models, tools


class StockMoveLine(models.Model):
    _inherit = "stock.move.line"

    def init(self):
        if not tools.index_exists(self._cr, "stock_move_line_stock_card_idx"):
            tools.create_index(
                self._cr,
                "stock_move_line_stock_aging_idx",
                self._table,
                ["company_id", "product_id", "date"],
                where="state = 'done'",
            )
        tools.create_index(
            self._cr,
            "stock_move_line_stock_aging_date_idx",
            self._table,
            ["company_id", "date"],
            where="state = 'done'",
        )
