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
# ถ้าไม่ฝัง ตัวอักษรไทยใน PDF จะกลายเป็นกล่องว่างทั้งหน้า
# ห้ามใส่ single-quote รอบชื่อ family หรือรอบ format(truetype): QWeb จะ escape
# เป็น &#39; แล้ว wkhtmltopdf อ่าน @font-face ไม่ออก ฟอนต์จะไม่ถูกฝัง
SARABUN_FONT_CSS = (
    "@font-face{font-family:Sarabun;font-weight:normal;"
    "src:url(data:font/truetype;base64,%s) format(truetype);}"
    "@font-face{font-family:Sarabun;font-weight:bold;"
    "src:url(data:font/truetype;base64,%s) format(truetype);}"
) % (_load_font_b64("Sarabun-Regular.ttf"), _load_font_b64("Sarabun-Bold.ttf"))


class ReportTrialBalance(models.AbstractModel):
    _name = "report.biz_ac_trial_balance.report_trial_balance_doc"
    _description = "Trial Balance PDF"

    @api.model
    def _get_report_values(self, docids, data=None):
        options = (data or {}).get("options") or {}
        report = self.env["biz.trial.balance.report"]
        report_data = report.get_report_data(options)
        columns = self._columns(report_data)
        return {
            "doc_ids": docids,
            "doc_model": "biz.trial.balance.wizard",
            "docs": self.env["biz.trial.balance.wizard"].browse(docids),
            "d": report_data,
            "columns": columns,
            "money_columns": [c for c in columns if c["type"] == "num"],
            "font_css": SARABUN_FONT_CSS,
            "printed_on": report.format_report_date(
                fields.Date.context_today(self),
                report_data["options"]["date_format"],
            ),
            "printed_by": self.env.user.name,
        }

    @api.model
    def _columns(self, report_data):
        """นิยามคอลัมน์ชุดเดียวกับ Excel เพื่อให้สองไฟล์อ่านคู่กันได้โดยไม่งง"""
        columns = [
            {"group": "", "label": "เลขที่บัญชี", "key": "code", "type": "text", "width": "9%"},
            {"group": "", "label": "ชื่อบัญชี", "key": "name", "type": "name", "width": "27%"},
        ]
        # โหมดแยกบริษัทต้องบอกให้ได้ว่าแถวไหนของใคร ไม่งั้นเห็นรหัสซ้ำแล้วงง
        if report_data["options"]["company_mode"] == "split" and report_data["company"]["count"] > 1:
            columns.append(
                {"group": "", "label": "บริษัท", "key": "company_name",
                 "type": "text", "width": "14%"}
            )
        columns += [
            {"group": "ยอดยกมา", "label": "เดบิต", "key": "opening_debit", "type": "num"},
            {"group": "ยอดยกมา", "label": "เครดิต", "key": "opening_credit", "type": "num"},
            {"group": "เปลี่ยนแปลง", "label": "เดบิต", "key": "period_debit", "type": "num"},
            {"group": "เปลี่ยนแปลง", "label": "เครดิต", "key": "period_credit", "type": "num"},
            {"group": "คงเหลือ", "label": "เดบิต", "key": "closing_debit", "type": "num"},
            {"group": "คงเหลือ", "label": "เครดิต", "key": "closing_credit", "type": "num"},
        ]
        if report_data["options"]["compare"] != "none":
            label = report_data["labels"]["compare"] or "เปรียบเทียบ"
            columns += [
                {"group": label, "label": "เดบิต", "key": "compare_debit", "type": "num"},
                {"group": label, "label": "เครดิต", "key": "compare_credit", "type": "num"},
            ]
        columns.append(
            {"group": "", "label": "เปลี่ยนแปลง %", "key": "change_pct", "type": "pct", "width": "8%"}
        )
        # จับคู่หัวคอลัมน์สองชั้น: colspan ของหัวกลุ่ม และตำแหน่งที่ต้อง rowspan
        index = 0
        while index < len(columns):
            group = columns[index]["group"]
            span = 1
            if group:
                while index + span < len(columns) and columns[index + span]["group"] == group:
                    span += 1
            columns[index]["group_span"] = span if group else 0
            columns[index]["group_first"] = True
            for offset in range(1, span):
                columns[index + offset]["group_span"] = 0
                columns[index + offset]["group_first"] = False
            index += span
        return columns
