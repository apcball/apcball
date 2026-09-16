# -*- coding: utf-8 -*-
"""ข้อมูลสำหรับ PDF งบการเงิน (QWeb + wkhtmltopdf)

ฟอนต์ไทยต้องฝังเป็น base64 ใน CSS — คอนเทนเนอร์ odoo:17.0 ไม่มีฟอนต์ไทย
ติดตั้งเลย ถ้าไม่ฝัง ตัวอักษรไทยจะกลายเป็นกล่องว่างทั้งหน้า
"""
import base64
import os

from odoo import api, fields, models

_FONT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "static", "fonts")


def _load_font_b64(filename):
    try:
        with open(os.path.join(_FONT_DIR, filename), "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")
    except OSError:
        return ""


# ห้ามใส่ single-quote รอบชื่อ family หรือรอบ format(truetype): QWeb จะ escape
# เป็น &#39; แล้ว wkhtmltopdf อ่าน @font-face ไม่ออก ฟอนต์จะไม่ถูกฝัง
SARABUN_FONT_CSS = (
    "@font-face{font-family:Sarabun;font-weight:normal;"
    "src:url(data:font/truetype;base64,%s) format(truetype);}"
    "@font-face{font-family:Sarabun;font-weight:bold;"
    "src:url(data:font/truetype;base64,%s) format(truetype);}"
) % (_load_font_b64("Sarabun-Regular.ttf"), _load_font_b64("Sarabun-Bold.ttf"))


class BsfStatementsReport(models.AbstractModel):
    _name = "report.biz_smart_finance.report_statements_doc"
    _description = "Smart Finance Statements PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env["biz.smart.finance.export.wizard"].browse(docids)
        filters = (data or {}).get("filters")
        if filters is None:
            filters = wizard[:1]._get_filters() if wizard else {}
        payload = self.env["biz.smart.finance.dashboard"].get_dashboard_data(
            filters)
        return {
            "doc_ids": docids,
            "doc_model": "biz.smart.finance.export.wizard",
            "docs": wizard,
            "d": payload,
            "st": payload["statements"],
            "co": payload["controlling"],
            # เปรียบเทียบหลายงวด — ปิดอยู่ = dict ที่ enabled เป็นเท็จ
            # (เทมเพลตเช็คเองก่อนวาด จึงไม่ต้องแตกเป็นรีพอร์ตคนละตัว)
            "cmp": payload.get("compare") or {},
            "f": payload["filters"],
            "font_css": SARABUN_FONT_CSS,
            "printed_by": self.env.user.name,
            "printed_on": fields.Datetime.to_string(fields.Datetime.now()),
            "aging_labels": [
                ("current", "Current"), ("b1_30", "1 - 30 วัน"),
                ("b31_60", "31 - 60 วัน"), ("b60_plus", "เกิน 60 วัน"),
            ],
        }
