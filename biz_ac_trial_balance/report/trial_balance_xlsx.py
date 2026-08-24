# -*- coding: utf-8 -*-
"""สร้างไฟล์ Excel ของงบทดลอง

ตัวเลขทั้งหมดมาจาก ``biz.trial.balance.report.get_report_data()`` โมดูลนี้ทำแค่จัดหน้า
จุดที่ตั้งใจออกแบบ:
* แถวรวมเป็นสูตร ``SUMPRODUCT`` คูณกับคอลัมน์ตัวช่วยที่ซ่อนไว้ ไม่ใช่ค่าตายตัว —
  ผู้สอบบัญชีกดดูสูตรแล้วตรวจย้อนได้ และแถวรวมหมวดจึงไม่ถูกนับซ้ำเข้ายอดรวม
"""

import io

from xlsxwriter.utility import xl_range

from odoo import _, api, fields, models
from odoo.tools.misc import xlsxwriter


class TrialBalanceXlsx(models.AbstractModel):
    _name = "biz.trial.balance.xlsx"
    _description = "Trial Balance XLSX Builder"

    @api.model
    def generate(self, options=None):
        report = self.env["biz.trial.balance.report"]
        data = report.get_report_data(options)

        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        fmt = self._formats(workbook, data["company"]["decimal_places"])
        self._sheet_main(workbook, fmt, data)
        self._sheet_summary(workbook, fmt, data)
        workbook.close()
        return buffer.getvalue()

    # ------------------------------------------------------------------
    def _formats(self, workbook, decimal_places):
        num = "#,##0." + "0" * decimal_places if decimal_places else "#,##0"
        base = {"font_name": "Sarabun", "font_size": 10}
        return {
            "title": workbook.add_format({**base, "font_size": 16, "bold": True}),
            "meta": workbook.add_format({**base, "font_size": 9, "font_color": "#555555"}),
            "meta_warn": workbook.add_format(
                {**base, "font_size": 9, "bold": True, "font_color": "#B42318"}
            ),
            "head": workbook.add_format({
                **base, "bold": True, "align": "center", "valign": "vcenter",
                "bg_color": "#F2F4F7", "border": 1, "text_wrap": True,
            }),
            "text": workbook.add_format({**base, "border": 1}),
            "text_indent": [
                workbook.add_format({**base, "border": 1, "indent": i}) for i in range(8)
            ],
            "num": workbook.add_format({**base, "border": 1, "num_format": num}),
            "pct": workbook.add_format({**base, "border": 1, "num_format": '0.0"%"'}),
            "section": workbook.add_format(
                {**base, "bold": True, "border": 1, "bg_color": "#EAECF0"}
            ),
            "section_num": workbook.add_format({
                **base, "bold": True, "border": 1, "bg_color": "#EAECF0", "num_format": num,
            }),
            "total": workbook.add_format({
                **base, "bold": True, "border": 1, "top": 6, "bg_color": "#D1E9FF",
            }),
            "total_num": workbook.add_format({
                **base, "bold": True, "border": 1, "top": 6, "bg_color": "#D1E9FF",
                "num_format": num,
            }),
            "abnormal": workbook.add_format({"font_color": "#B42318", "bold": True}),
        }

    # ------------------------------------------------------------------
    def _columns(self, data):
        """(หัวกลุ่ม, หัวย่อย, ความกว้าง, คีย์ในแถวข้อมูล, ชนิด)"""
        cols = [
            ("", _("เลขที่บัญชี"), 14, "code", "text"),
            ("", _("ชื่อบัญชี"), 42, "name", "name"),
        ]
        # โหมดแยกบริษัท: แทรกคอลัมน์บริษัทไว้หลังชื่อบัญชี — คอลัมน์ 0/1 ต้องคงที่
        # เพราะ _write_total() เขียนคำว่า "รวมทั้งสิ้น" ลงที่ index 1 ตรง ๆ
        if data["options"]["company_mode"] == "split" and data["company"]["count"] > 1:
            cols.append(("", _("บริษัท"), 22, "company_name", "text"))
        cols += [
            (_("ยอดยกมา"), _("เดบิต"), 16, "opening_debit", "num"),
            (_("ยอดยกมา"), _("เครดิต"), 16, "opening_credit", "num"),
            (_("เปลี่ยนแปลง"), _("เดบิต"), 16, "period_debit", "num"),
            (_("เปลี่ยนแปลง"), _("เครดิต"), 16, "period_credit", "num"),
            (_("คงเหลือ"), _("เดบิต"), 16, "closing_debit", "num"),
            (_("คงเหลือ"), _("เครดิต"), 16, "closing_credit", "num"),
        ]
        if data["options"]["compare"] != "none":
            label = data["labels"]["compare"] or _("เปรียบเทียบ")
            cols += [
                (label, _("เดบิต"), 16, "compare_debit", "num"),
                (label, _("เครดิต"), 16, "compare_credit", "num"),
            ]
        cols += [
            ("", _("เปลี่ยนแปลง %"), 14, "change_pct", "pct"),
            ("", _("สถานะ"), 12, "flag", "flag"),
        ]
        return cols

    def _sheet_main(self, workbook, fmt, data):
        sheet = workbook.add_worksheet(_("งบทดลอง"))
        sheet.set_landscape()
        sheet.set_paper(9)  # A4
        sheet.fit_to_pages(1, 0)
        sheet.outline_settings(True, False, False, False)

        cols = self._columns(data)
        for index, (_group, _sub, width, _key, _kind) in enumerate(cols):
            sheet.set_column(index, index, width)
        helper_col = len(cols)
        sheet.set_column(helper_col, helper_col, None, None, {"hidden": True})

        row = self._write_meta(sheet, fmt, data, len(cols))
        head_row = row
        row = self._write_header(sheet, fmt, cols, row)
        first_data_row = row

        labels = {
            "ok": "",
            "abnormal": _("ยอดผิดด้าน"),
            "unbalanced": _("ไม่ดุล"),
        }
        for line in data["lines"]:
            kind = line["kind"]
            is_section = kind in ("section", "section_total")
            text_fmt = fmt["section"] if is_section else None
            num_fmt = fmt["section_num"] if is_section else fmt["num"]
            # แถวหัวหมวดเป็นแค่ป้ายกำกับ ไม่มีตัวเลขของตัวเอง เว้นช่องไว้ให้อ่านง่าย
            is_label_only = kind == "section"
            for index, (_group, _sub, _width, key, ctype) in enumerate(cols):
                if ctype == "num":
                    if is_label_only:
                        sheet.write_blank(row, index, None, num_fmt)
                    else:
                        sheet.write_number(row, index, line.get(key) or 0.0, num_fmt)
                elif ctype == "pct":
                    pct_fmt = fmt["section"] if is_section else fmt["pct"]
                    value = None if is_label_only else line.get(key)
                    if value is None:
                        sheet.write_blank(row, index, None, pct_fmt)
                    else:
                        sheet.write_number(row, index, value, pct_fmt)
                elif ctype == "flag":
                    sheet.write_string(row, index, labels.get(line.get("flag"), ""),
                                       text_fmt or fmt["text"])
                elif ctype == "name":
                    indent = min(max(line.get("level", 0), 0), 7)
                    sheet.write_string(
                        row, index, line.get("name") or "",
                        text_fmt or fmt["text_indent"][indent],
                    )
                else:
                    sheet.write_string(row, index, str(line.get(key) or ""),
                                       text_fmt or fmt["text"])
            sheet.write_number(row, helper_col, 1 if line.get("counts_to_total") else 0)
            row += 1

        last_data_row = row - 1
        self._write_total(sheet, fmt, cols, data, row, first_data_row, last_data_row, helper_col)
        sheet.freeze_panes(head_row + 2, 2)
        sheet.repeat_rows(head_row, head_row + 1)
        # ไม่ใส่ autofilter: หัวตารางเป็นเซลล์ merge สองแถว ซึ่ง Excel มักฟ้องว่าไฟล์เสีย
        # และการกรองแถวในรายงานที่มีแถวรวมหมวดคั่นอยู่ก็ให้ผลที่อ่านผิดได้ง่าย

    # ------------------------------------------------------------------
    def _write_meta(self, sheet, fmt, data, ncols):
        labels = data["labels"]
        options = data["options"]
        sheet.write(0, 0, data["company"]["names"], fmt["title"])
        sheet.write(1, 0, "%s  %s" % (labels["title"], labels["period"]), fmt["title"])
        meta = [
            "%s: %s" % (_("แสดงข้อมูล"), labels["closing_mode"]),
            "%s: %s" % (_("เกณฑ์ยอดยกมา"), labels["opening_basis"]),
            "%s: %s" % (_("สถานะรายการ"), labels["target_move"]),
            "%s: %s" % (_("แสดงบัญชี"), labels["display_account"]),
        ]
        if labels["compare"]:
            meta.append(labels["compare"])
        if labels["company_mode"]:
            meta.append("%s: %s" % (_("งบหลายบริษัท"), labels["company_mode"]))
        meta.append("%s: %s  %s: %s" % (
            _("พิมพ์เมื่อ"),
            self.env["biz.trial.balance.report"].format_report_date(
                fields.Date.context_today(self), options["date_format"]
            ),
            _("โดย"), self.env.user.name,
        ))
        sheet.write(2, 0, "   |   ".join(meta), fmt["meta"])
        row = 3
        if data["checks"]["include_draft"]:
            sheet.write(row, 0, _(
                "คำเตือน: รายงานนี้รวมรายการที่ยังไม่ผ่านรายการ (Draft) — ห้ามใช้ยื่นงบการเงิน"
            ), fmt["meta_warn"])
            row += 1
        if data["checks"]["mixed_currency"]:
            sheet.write(row, 0, _(
                "คำเตือน: มีบริษัทที่ใช้สกุลเงินต่างจากรายงานนี้ ยอดถูกบวกกันตรง ๆ โดยไม่แปลงค่า: %s"
            ) % ", ".join(
                "%s (%s)" % (c["name"], c["currency"])
                for c in data["checks"]["mixed_currency"]
            ), fmt["meta_warn"])
            row += 1
        if not data["checks"]["is_balanced"]:
            sheet.write(row, 0, _("คำเตือน: เดบิตรวมไม่เท่ากับเครดิตรวม ผลต่าง %s") % (
                data["checks"]["difference"],
            ), fmt["meta_warn"])
            row += 1
        return row + 1

    def _write_header(self, sheet, fmt, cols, row):
        index = 0
        while index < len(cols):
            group = cols[index][0]
            span = 1
            if group:
                while index + span < len(cols) and cols[index + span][0] == group:
                    span += 1
            if group and span > 1:
                sheet.merge_range(row, index, row, index + span - 1, group, fmt["head"])
            elif group:
                sheet.write(row, index, group, fmt["head"])
            else:
                sheet.merge_range(row, index, row + 1, index, cols[index][1], fmt["head"])
            for offset in range(span):
                if group:
                    sheet.write(row + 1, index + offset, cols[index + offset][1], fmt["head"])
            index += span
        sheet.set_row(row, 20)
        sheet.set_row(row + 1, 20)
        return row + 2

    def _write_total(self, sheet, fmt, cols, data, row, first, last, helper_col):
        totals = data["totals"]
        helper = xl_range(first, helper_col, last, helper_col)
        for index, (_group, _sub, _width, key, ctype) in enumerate(cols):
            if ctype == "num":
                value_range = xl_range(first, index, last, index)
                sheet.write_formula(
                    row, index,
                    "=SUMPRODUCT(%s,%s)" % (helper, value_range),
                    fmt["total_num"], totals.get(key) or 0.0,
                )
            elif ctype == "pct":
                sheet.write_blank(row, index, None, fmt["total_num"])
            elif index == 1:
                sheet.write_string(row, index, _("รวมทั้งสิ้น"), fmt["total"])
            elif ctype == "flag":
                sheet.write_string(
                    row, index,
                    _("สมดุล") if data["checks"]["is_balanced"] else _("ไม่สมดุล"),
                    fmt["total"],
                )
            else:
                sheet.write_string(row, index, "", fmt["total"])

    # ------------------------------------------------------------------
    def _sheet_summary(self, workbook, fmt, data):
        """สรุปยอดรวมรายหมวด + ผลตรวจดุล สำหรับแนบหน้าแรกของแฟ้มปิดงวด"""
        sheet = workbook.add_worksheet(_("สรุปตามหมวด"))
        sheet.set_column(0, 0, 30)
        sheet.set_column(1, 4, 18)
        sheet.write(0, 0, "%s — %s" % (data["labels"]["title"], _("สรุปตามหมวดบัญชี")), fmt["title"])
        sheet.write(1, 0, data["labels"]["period"], fmt["meta"])

        row = 3
        for index, label in enumerate(
            [_("หมวดบัญชี"), _("ยอดยกมา (สุทธิ)"), _("เปลี่ยนแปลง (สุทธิ)"), _("คงเหลือ (สุทธิ)")]
        ):
            sheet.write(row, index, label, fmt["head"])
        row += 1
        for line in data["lines"]:
            if line["kind"] != "section_total":
                continue
            sheet.write_string(row, 0, line["name"], fmt["text"])
            sheet.write_number(row, 1, line["opening_debit"] - line["opening_credit"], fmt["num"])
            sheet.write_number(row, 2, line["period_debit"] - line["period_credit"], fmt["num"])
            sheet.write_number(row, 3, line["closing_debit"] - line["closing_credit"], fmt["num"])
            row += 1

        row += 1
        checks = data["checks"]
        sheet.write_string(row, 0, _("เดบิตรวม"), fmt["text"])
        sheet.write_number(row, 1, data["totals"]["closing_debit"], fmt["num"])
        sheet.write_string(row + 1, 0, _("เครดิตรวม"), fmt["text"])
        sheet.write_number(row + 1, 1, data["totals"]["closing_credit"], fmt["num"])
        sheet.write_string(row + 2, 0, _("ผลต่าง"), fmt["total"])
        sheet.write_number(row + 2, 1, checks["difference"], fmt["total_num"])
        sheet.write_string(
            row + 3, 0,
            _("ผลตรวจดุล: สมดุล") if checks["is_balanced"] else _("ผลตรวจดุล: ไม่สมดุล"),
            fmt["total"] if checks["is_balanced"] else fmt["meta_warn"],
        )
        sheet.write_string(row + 4, 0, _("กำไร(ขาดทุน)สุทธิของงวด"), fmt["text"])
        sheet.write_number(row + 4, 1, data["totals"].get("net_profit") or 0.0, fmt["num"])

        if checks["unbalanced_moves"]:
            row += 6
            sheet.write_string(row, 0, _("รายการที่เดบิตไม่เท่าเครดิต"), fmt["meta_warn"])
            for move in checks["unbalanced_moves"]:
                row += 1
                sheet.write_string(row, 0, move["name"] or "", fmt["text"])
                sheet.write_number(row, 1, move["difference"], fmt["num"])
