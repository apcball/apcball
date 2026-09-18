# -*- coding: utf-8 -*-
"""สร้างไฟล์ Excel ของสต๊อกการ์ด

ตัวเลขทั้งหมดมาจาก ``biz.stock.card.report.get_report_data()`` โมดูลนี้ทำแค่จัดหน้า
จุดที่ตั้งใจออกแบบ:

* แถวรวมเป็นสูตร ``SUMPRODUCT`` คูณกับคอลัมน์ตัวช่วยที่ซ่อนไว้ ไม่ใช่ค่าตายตัว —
  ผู้ตรวจสอบกดดูสูตรแล้วตรวจย้อนได้ และแถวรวมกลุ่ม/แถวรายการเคลื่อนไหวจึงไม่ถูก
  นับซ้ำเข้ายอดรวม (ตัวช่วยคือ ``counts_to_total`` ซึ่งเป็นจริงเฉพาะแถวระดับบนสุด)
* ไม่ใส่ autofilter — หัวตารางเป็นเซลล์ merge สองแถว ซึ่ง Excel มักฟ้องว่าไฟล์เสีย
  และการกรองชีตที่มีแถวรวมแทรกอยู่ให้ภาพที่ชวนเข้าใจผิด
"""

import io

from xlsxwriter.utility import xl_range

from odoo import _, api, fields, models
from odoo.tools.misc import xlsxwriter


class StockCardXlsx(models.AbstractModel):
    _name = "biz.stock.card.xlsx"
    _description = "Stock Card XLSX Builder"

    @api.model
    def generate(self, options=None):
        report = self.env["biz.stock.card.report"]
        data = report.get_report_data(options)
        columns = report.report_columns(data)

        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        fmt = self._formats(
            workbook, data["company"]["decimal_places"], data["company"]["qty_precision"]
        )
        self._sheet_main(workbook, fmt, data, columns)
        self._sheet_warehouse(workbook, fmt, data, columns)
        self._sheet_notes(workbook, fmt, data)
        workbook.close()
        return buffer.getvalue()

    # ------------------------------------------------------------------
    def _formats(self, workbook, decimal_places, qty_precision):
        money = "#,##0." + "0" * decimal_places if decimal_places else "#,##0"
        qty = "#,##0." + "0" * qty_precision if qty_precision else "#,##0"
        base = {"font_name": "Sarabun", "font_size": 10}
        formats = {
            "title": workbook.add_format({**base, "font_size": 16, "bold": True}),
            "subtitle": workbook.add_format({**base, "font_size": 12, "bold": True}),
            "meta": workbook.add_format({**base, "font_size": 9, "font_color": "#555555"}),
            "meta_warn": workbook.add_format(
                {**base, "font_size": 9, "bold": True, "font_color": "#B42318"}
            ),
            "meta_ok": workbook.add_format(
                {**base, "font_size": 9, "bold": True, "font_color": "#027A48"}
            ),
            "head": workbook.add_format({
                **base, "bold": True, "align": "center", "valign": "vcenter",
                "bg_color": "#F2F4F7", "border": 1, "text_wrap": True,
            }),
            "text": workbook.add_format({**base, "border": 1}),
            "text_indent": [
                workbook.add_format({**base, "border": 1, "indent": i}) for i in range(8)
            ],
            "date": workbook.add_format({**base, "border": 1}),
            "qty": workbook.add_format({**base, "border": 1, "num_format": qty}),
            "money": workbook.add_format({**base, "border": 1, "num_format": money}),
        }
        # แถวกลุ่มแต่ละระดับมีเฉดของตัวเอง เพื่อให้อ่านลำดับชั้นออกในไฟล์แบน ๆ
        for level, colour in enumerate(("#EAECF0", "#F2F4F7", "#F9FAFB")):
            formats["group_text_%s" % level] = [
                workbook.add_format({
                    **base, "bold": True, "border": 1, "bg_color": colour, "indent": i,
                }) for i in range(8)
            ]
            formats["group_qty_%s" % level] = workbook.add_format({
                **base, "bold": True, "border": 1, "bg_color": colour, "num_format": qty,
            })
            formats["group_money_%s" % level] = workbook.add_format({
                **base, "bold": True, "border": 1, "bg_color": colour, "num_format": money,
            })
        formats["total_text"] = workbook.add_format({
            **base, "bold": True, "border": 1, "top": 6, "bg_color": "#D1E9FF",
        })
        formats["total_qty"] = workbook.add_format({
            **base, "bold": True, "border": 1, "top": 6, "bg_color": "#D1E9FF",
            "num_format": qty,
        })
        formats["total_money"] = workbook.add_format({
            **base, "bold": True, "border": 1, "top": 6, "bg_color": "#D1E9FF",
            "num_format": money,
        })
        return formats

    # ------------------------------------------------------------------
    def _sheet_main(self, workbook, fmt, data, columns):
        sheet = workbook.add_worksheet(_("สต๊อกการ์ด"))
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 1, 44)
        sheet.set_column(2, len(columns) - 1, 14)

        row = self._write_header_block(sheet, fmt, data, len(columns))
        head_row = row
        row = self._write_table_head(sheet, fmt, columns, head_row)

        # คอลัมน์ตัวช่วย 0/1 ที่ซ่อนไว้ ทำให้ยอดรวมเป็นสูตรที่ตรวจย้อนได้
        helper_col = len(columns)
        sheet.set_column(helper_col, helper_col, None, None, {"hidden": True})
        sheet.write(head_row, helper_col, "counts_to_total", fmt["meta"])

        first_data_row = row
        for line in data["lines"]:
            self._write_line(sheet, fmt, columns, row, line, data)
            sheet.write_number(row, helper_col, 1 if line.get("counts_to_total") else 0)
            row += 1
        last_data_row = row - 1

        if last_data_row >= first_data_row:
            self._write_total(sheet, fmt, columns, data, row, first_data_row,
                              last_data_row, helper_col)
        sheet.freeze_panes(head_row + 2, 2)
        sheet.repeat_rows(head_row, head_row + 1)

    def _write_header_block(self, sheet, fmt, data, width):
        labels = data["labels"]
        checks = data["checks"]
        sheet.write(0, 0, data["company"]["names"], fmt["title"])
        sheet.write(1, 0, "%s %s" % (labels["title"], labels["period"]), fmt["subtitle"])
        row = 2
        for text in (
            _("จัดกลุ่ม: %s") % labels["levels"],
            _("คลัง: %s") % labels["warehouses"],
            _("ยอดยกมา: %s") % labels["opening_basis"],
            _("มูลค่า: %s (เกณฑ์วันที่: %s)") % (labels["value_mode"], labels["value_date_basis"]),
            _("เขตเวลา: %s") % labels["timezone"],
        ):
            sheet.write(row, 0, text, fmt["meta"])
            row += 1
        if data["options"]["show_value"]:
            if checks["svl_scope_limited"]:
                sheet.write(row, 0, _(
                    "หมายเหตุ: รายงานถูกกรองคลัง/ที่เก็บ และชั้นมูลค่าสินค้า (SVL) "
                    "ไม่มีมิติคลัง จึงกระทบยอดกับมูลค่าทั้งบริษัทไม่ได้"
                ), fmt["meta"])
            else:
                style = fmt["meta_ok"] if checks["svl_reconciled"] else fmt["meta_warn"]
                sheet.write(row, 0, _(
                    "มูลค่าในงวดตามชั้นมูลค่าสินค้า (SVL): %s / ในรายงาน: %s / ผลต่าง: %s"
                ) % (
                    checks["svl_period_value"], checks["report_period_value"],
                    checks["svl_difference"],
                ), style)
            row += 1
        if checks["balance_broken_by_filter"]:
            sheet.write(row, 0, _(
                "คำเตือน: ตัวกรองตัดการปรับปรุงยอดหรือของเสียออก "
                "สมการ คงเหลือ = ยกมา + รับ − จ่าย จึงไม่เป็นจริง"
            ), fmt["meta_warn"])
            row += 1
        return row + 1

    def _write_table_head(self, sheet, fmt, columns, head_row):
        for index, col in enumerate(columns):
            if col["group"]:
                if col["group_span"]:
                    if col["group_span"] > 1:
                        sheet.merge_range(
                            head_row, index, head_row, index + col["group_span"] - 1,
                            col["group"], fmt["head"],
                        )
                    else:
                        sheet.write(head_row, index, col["group"], fmt["head"])
                sheet.write(head_row + 1, index, col["label"], fmt["head"])
            else:
                sheet.merge_range(
                    head_row, index, head_row + 1, index, col["label"], fmt["head"]
                )
        return head_row + 2

    def _write_line(self, sheet, fmt, columns, row, line, data):
        kind = line["kind"]
        level = min(line.get("level") or 0, 7)
        shade = min(level, 2) if kind in ("group", "group_total") else None
        for index, col in enumerate(columns):
            ctype = col["type"]
            if ctype == "text":
                value = (
                    line.get("date_display") if kind in ("move", "more") else line.get("code")
                ) or ""
                style = fmt["group_text_%s" % shade][0] if shade is not None else fmt["text"]
                sheet.write_string(row, index, value, style)
            elif ctype == "name":
                style = (
                    fmt["group_text_%s" % shade][level] if shade is not None
                    else fmt["text_indent"][level]
                )
                sheet.write_string(row, index, line.get("name") or "", style)
            elif ctype == "uom":
                style = fmt["group_text_%s" % shade][0] if shade is not None else fmt["text"]
                sheet.write_string(row, index, line.get("uom_name") or "", style)
            else:
                style = (
                    fmt["group_%s_%s" % (ctype, shade)] if shade is not None else fmt[ctype]
                )
                value = line.get(col["key"])
                if value:
                    sheet.write_number(row, index, value, style)
                else:
                    sheet.write_blank(row, index, None, style)

    def _write_total(self, sheet, fmt, columns, data, row, first, last, helper_col):
        helper = xl_range(first, helper_col, last, helper_col)
        totals = data["totals"]
        for index, col in enumerate(columns):
            if col["type"] in ("qty", "money"):
                style = fmt["total_qty"] if col["type"] == "qty" else fmt["total_money"]
                if col["key"].startswith("balance_"):
                    # ยอดคงเหลือสะสมเป็นค่าของแต่ละบรรทัด รวมกันไม่มีความหมาย
                    sheet.write_blank(row, index, None, style)
                    continue
                value_range = xl_range(first, index, last, index)
                sheet.write_formula(
                    row, index,
                    "=SUMPRODUCT(%s,%s)" % (helper, value_range),
                    style,
                    # ค่าที่แคชไว้ ทำให้โปรแกรมที่ไม่คำนวณสูตรใหม่ยังเห็นตัวเลขถูก
                    totals.get(col["key"]) or 0.0,
                )
            elif col["type"] == "name":
                sheet.write_string(row, index, totals["name"], fmt["total_text"])
            elif col["type"] == "uom":
                sheet.write_blank(row, index, None, fmt["total_text"])
            else:
                sheet.write_blank(row, index, None, fmt["total_text"])

    # ------------------------------------------------------------------
    def _sheet_warehouse(self, workbook, fmt, data, columns):
        """สรุปเฉพาะแถวระดับบนสุด — ชุดเดียวกับที่ SUMPRODUCT ใช้รวมยอด"""
        sheet = workbook.add_worksheet(_("สรุประดับบนสุด"))
        sheet.set_column(0, 0, 18)
        sheet.set_column(1, 1, 44)
        sheet.set_column(2, len(columns) - 1, 14)
        sheet.write(0, 0, _("สรุปตาม %s") % data["levels"][0]["label"], fmt["title"])
        head_row = 2
        self._write_table_head(sheet, fmt, columns, head_row)
        row = head_row + 2
        for line in data["lines"]:
            if not line.get("counts_to_total"):
                continue
            self._write_line(sheet, fmt, columns, row, line, data)
            row += 1
        for index, col in enumerate(columns):
            if col["type"] in ("qty", "money") and not col["key"].startswith("balance_"):
                style = fmt["total_qty"] if col["type"] == "qty" else fmt["total_money"]
                sheet.write_number(row, index, data["totals"].get(col["key"]) or 0.0, style)
            elif col["type"] == "name":
                sheet.write_string(row, index, data["totals"]["name"], fmt["total_text"])
            else:
                sheet.write_blank(row, index, None, fmt["total_text"])
        sheet.freeze_panes(head_row + 2, 2)

    # ------------------------------------------------------------------
    def _sheet_notes(self, workbook, fmt, data):
        """ข้อสังเกตทั้งหมดเป็นภาษาไทย — สิ่งที่ต้องรู้ก่อนเชื่อตัวเลขในไฟล์นี้"""
        sheet = workbook.add_worksheet(_("ข้อสังเกต"))
        sheet.set_column(0, 0, 34)
        sheet.set_column(1, 1, 76)
        checks = data["checks"]
        sheet.write(0, 0, _("ข้อสังเกตของรายงานฉบับนี้"), fmt["title"])

        rows = [(_("จำนวนกลุ่มในรายงาน"), str(checks["group_count"]))]
        if data["options"]["show_value"]:
            if checks["svl_scope_limited"]:
                verdict = _("(กระทบยอดไม่ได้ เพราะรายงานถูกกรองคลัง/ที่เก็บ)")
            elif checks["svl_reconciled"]:
                verdict = _("(กระทบยอดได้)")
            else:
                verdict = _("(ไม่กระทบยอด!)")
            rows += [
                (_("มูลค่าในงวดตาม SVL"), "%s" % checks["svl_period_value"]),
                (_("มูลค่าในงวดตามรายงาน"), "%s" % checks["report_period_value"]),
                (_("ผลต่าง"), "%s %s" % (checks["svl_difference"], verdict)),
                (_("มูลค่าประมาณของการโอนภายใน"), "%s (%s บรรทัด)" % (
                    checks["imputed_internal"]["value"], checks["imputed_internal"]["line_count"],
                )),
                (_("วิธีคิดมูลค่า"), data["labels"]["value_mode"]),
                (_("เกณฑ์วันที่ของมูลค่า"), data["labels"]["value_date_basis"]),
                (_("มูลค่าระดับคลัง"), _(
                    "แม่นยำ — อ่านจาก stock.valuation.layer.warehouse_id ตรงตัว "
                    "(ติดตั้ง stock_fifo_by_location)"
                ) if checks["svl_warehouse_exact"] else _(
                    "ประมาณ — กระจายตามสัดส่วนจำนวน เพราะ SVL ไม่มีมิติคลังบนระบบนี้"
                )),
            ]
            if checks["value_date_basis_downgraded"]:
                rows.append((_("หมายเหตุ"), _(
                    "ขอเกณฑ์วันที่บัญชี (accounting_date) แต่ระบบนี้ไม่มีฟิลด์นั้น "
                    "จึงลดระดับไปใช้วันที่ของการเคลื่อนไหวแทน"
                )))
        else:
            rows.append((_("มูลค่า"), _("ไม่แสดง — ผู้ใช้ไม่มีสิทธิ์ดูมูลค่าสินค้า")))
        rows.append((_("การโอนข้ามคลัง"), _(
            "%s บรรทัด รวม %s หน่วย — ยอด รับ/จ่าย นับสองครั้งโดยตั้งใจ "
            "(จ่ายออกของคลังต้นทาง + รับเข้าของคลังปลายทาง) ยอดยกมาและคงเหลือไม่กระทบ"
        ) % (checks["interwarehouse"]["line_count"], checks["interwarehouse"]["qty"])))
        if checks["balance_broken_by_filter"]:
            rows.append((_("คำเตือน"), _(
                "ตัวกรองตัดการปรับปรุงยอดหรือของเสียออก "
                "สมการ คงเหลือ = ยกมา + รับ − จ่าย ไม่เป็นจริงในรายงานนี้"
            )))
        if checks["detail_downgraded"]:
            rows.append((_("หมายเหตุ"), _(
                "ขอให้แสดงรายการเคลื่อนไหวทั้งหมดโดยไม่ได้กรองสินค้าหรือหมวด "
                "ระบบจึงลดเหลือเฉพาะกลุ่มที่กางอยู่"
            )))
        if checks["date_from_downgraded"]:
            rows.append((_("หมายเหตุ"), _(
                "วันที่เริ่มต้นก่อนวัน cutoff (%s) ยอดยกมาก่อนหน้านั้นไม่น่าเชื่อถือ "
                "ระบบจึงตัดวันเริ่มต้นให้เป็นวัน cutoff แทน ตรงกับ Stock FIFO Valuation Report"
            ) % checks["cutoff_date"]))
        if checks["truncated_leaves"]:
            rows.append((_("คำเตือน"), _(
                "%s กลุ่มแสดงรายการเคลื่อนไหวไม่ครบ (เกินขีดจำกัดต่อกลุ่ม) "
                "แถวปิดท้ายถือยอดที่เหลือไว้แล้ว ยอดคงเหลือสะสมจึงยังถูกต้อง"
            ) % checks["truncated_leaves"]))
        if checks["opening_skipped"]:
            rows.append((_("หมายเหตุ"), _("ไม่ได้คำนวณยอดยกมาตามที่เลือกไว้")))
        for company in checks["mixed_currency"]:
            rows.append((_("คำเตือน: คนละสกุลเงิน"), _(
                "%s ใช้สกุล %s ยอดถูกบวกกันตรง ๆ โดยไม่แปลงค่า"
            ) % (company["name"], company["currency"])))
        for negative in checks["negative_balances"]:
            rows.append((_("ยอดติดลบ"), "%s: %s" % (negative["name"], negative["qty"])))

        row = 2
        for label, value in rows:
            warn = label.startswith(_("คำเตือน")) or label == _("ยอดติดลบ")
            sheet.write_string(row, 0, label, fmt["text"])
            sheet.write_string(row, 1, value, fmt["meta_warn"] if warn else fmt["text"])
            row += 1
