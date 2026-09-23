# -*- coding: utf-8 -*-
"""ตัวเตรียมข้อมูลของรายงาน PDF — เรียกเครื่องยนต์ตัวเดียวกับหน้าจอและ Excel"""

import base64
import os

from odoo import api, fields, models

_FONT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "fonts")


def _load_font_b64(filename):
    try:
        with open(os.path.join(_FONT_DIR, filename), "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")
    except OSError:
        return ""


# ฝังฟอนต์เป็น base64 ตรงใน CSS — คอนเทนเนอร์ odoo:17.0 ไม่มีฟอนต์ไทยติดตั้งเลย
# ห้ามใส่ single-quote รอบชื่อ family หรือ format(truetype): QWeb จะ escape เป็น &#39;
# แล้ว wkhtmltopdf อ่าน @font-face ไม่ออก ฟอนต์จะไม่ถูกฝังโดยไม่มี error ใด ๆ
SARABUN_FONT_CSS = (
    "@font-face{font-family:Sarabun;font-weight:normal;"
    "src:url(data:font/truetype;base64,%s) format(truetype);}"
    "@font-face{font-family:Sarabun;font-weight:bold;"
    "src:url(data:font/truetype;base64,%s) format(truetype);}"
) % (_load_font_b64("Sarabun-Regular.ttf"), _load_font_b64("Sarabun-Bold.ttf"))


# wkhtmltopdf กับตารางหลายพันแถวใช้เวลาเป็นนาที — เพดานต่ำกว่าหน้าจอ (5,000) และ Excel (100,000)
PDF_MAX_LINES = 3000


class ReportStockAging(models.AbstractModel):
    _name = "report.biz_st_aging.report_stock_aging_doc"
    _description = "Stock Aging PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        options = dict((data or {}).get("options") or {}, max_lines=PDF_MAX_LINES)
        report = self.env["biz.stock.aging.report"]
        report_data = report.get_report_data(options)
        return {
            "doc_ids": docids,
            "doc_model": "biz.stock.aging.wizard",
            "docs": self.env["biz.stock.aging.wizard"].browse(docids),
            "d": report_data,
            "columns": report_data["columns"],
            "qty_precision": report_data["company"]["qty_precision"],
            "decimal_places": report_data["company"]["decimal_places"],
            "status_labels": report_data["status_labels"],
            "font_css": SARABUN_FONT_CSS,
            "printed_on": report.format_report_date(
                fields.Date.context_today(self),
                report_data["options"]["date_format"],
            ),
            "printed_by": self.env.user.name,
        }
