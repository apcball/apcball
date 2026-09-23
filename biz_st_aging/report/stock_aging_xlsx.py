# -*- coding: utf-8 -*-
"""สร้างไฟล์ Excel ของรายงานอายุสินค้าคงเหลือ

ตัวเลขทั้งหมดมาจาก ``biz.stock.aging.report.get_report_data()`` โมดูลนี้ทำแค่จัดหน้า

* แถวรวมของคอลัมน์ที่บวกได้ (``additive``) เป็นสูตร ``SUMPRODUCT`` คูณกับคอลัมน์ตัวช่วยที่ซ่อนไว้
  (``counts_to_total`` = แถวระดับบนสุด) ผู้ตรวจสอบกดดูสูตรแล้วตรวจย้อนได้ และแถวรวมกลุ่ม
  ไม่ถูกนับซ้ำ; คอลัมน์ที่บวกไม่ได้ (อายุเฉลี่ย / No Move / MOS / สถานะ) เขียนค่าจาก totals ตรง ๆ
* ไม่ใส่ autofilter — หัวตารางเป็นเซลล์ merge สองแถว
"""

import io

from xlsxwriter.utility import xl_range

from odoo import _, api, models
from odoo.tools.misc import xlsxwriter


# xlsxwriter เขียนแถวหลักหมื่นได้สบาย — เพดานสูงกว่าหน้าจอ (5,000) และ PDF (3,000)
XLSX_MAX_LINES = 100000


class StockAgingXlsx(models.AbstractModel):
    _name = "biz.stock.aging.xlsx"
    _description = "Stock Aging XLSX Builder"

    @api.model
    def generate(self, options=None):
        data = self.env["biz.stock.aging.report"].get_report_data(
            dict(options or {}, max_lines=XLSX_MAX_LINES)
        )
        columns = data["columns"]

        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        fmt = self._formats(
            workbook, data["company"]["decimal_places"], data["company"]["qty_precision"]
        )
        self._sheet_main(workbook, fmt, data, columns)
        self._sheet_buckets(workbook, fmt, data)
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
            "center": workbook.add_format({**base, "border": 1, "align": "center"}),
            "text_indent": [
                workbook.add_format({**base, "border": 1, "indent": i}) for i in range(8)
            ],
            "qty": workbook.add_format({**base, "border": 1, "num_format": qty}),
            "money": workbook.add_format({**base, "border": 1, "num_format": money}),
            "days": workbook.add_format({**base, "border": 1, "num_format": "#,##0"}),
            "months": workbook.add_format({**base, "border": 1, "num_format": "#,##0.0"}),
            "pct": workbook.add_format({**base, "border": 1, "num_format": "0.0"}),
        }
        for bucket, colour in enumerate(
            ("#ECFDF3", "#F0FDF4", "#FFFAEB", "#FEF0C7", "#FEE4E2", "#FECDCA")
        ):
            formats["head_b%d" % bucket] = workbook.add_format({
                **base, "bold": True, "align": "center", "valign": "vcenter",
                "bg_color": colour, "border": 1, "text_wrap": True,
            })
        for level, colour in enumerate(("#EAECF0", "#F2F4F7", "#F9FAFB")):
            formats["group_text_%s" % level] = [
                workbook.add_format({
                    **base, "bold": True, "border": 1, "bg_color": colour, "indent": i,
                }) for i in range(8)
            ]
            formats["group_center_%s" % level] = workbook.add_format({
                **base, "bold": True, "border": 1, "bg_color": colour, "align": "center",
            })
            for ctype, num in (("qty", qty), ("money", money), ("days", "#,##0"),
                               ("months", "#,##0.0")):
                formats["group_%s_%s" % (ctype, level)] = workbook.add_format({
                    **base, "bold": True, "border": 1, "bg_color": colour, "num_format": num,
                })
        total_base = {**base, "bold": True, "border": 1, "top": 6, "bg_color": "#D1E9FF"}
        formats["total_text"] = workbook.add_format(total_base)
        formats["total_center"] = workbook.add_format({**total_base, "align": "center"})
        for ctype, num in (("qty", qty), ("money", money), ("days", "#,##0"),
                           ("months", "#,##0.0")):
            formats["total_%s" % ctype] = workbook.add_format({**total_base, "num_format": num})
        return formats

    # ------------------------------------------------------------------
    def _sheet_main(self, workbook, fmt, data, columns):
        sheet = workbook.add_worksheet(_("อายุสินค้าคงเหลือ"))
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.set_column(0, 0, 16)
        sheet.set_column(1, 1, 40)
        sheet.set_column(2, len(columns) - 1, 12)

        row = self._write_header_block(sheet, fmt, data, len(columns))
        head_row = row
        row = self._write_table_head(sheet, fmt, columns, head_row)

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
        kpis = data["kpis"]
        sheet.write(0, 0, data["company"]["names"], fmt["title"])
        sheet.write(1, 0, "%s %s" % (labels["title"], labels["as_of"]), fmt["subtitle"])
        row = 2
        for text in (
            _("จัดกลุ่ม: %s") % labels["levels"],
            _("คลัง: %s") % labels["warehouses"],
            _("หลักการอายุ: %s (นับที่ระดับ %s)") % (labels["age_basis"], checks["age_granularity"]),
            _("มูลค่า: %s") % labels["cost_basis"],
            labels["usage_window"],
            _("เกณฑ์สถานะ: %s") % labels["thresholds"],
            _("ตัวกรอง: %s") % labels["filters"],
            _("เขตเวลา: %s") % labels["timezone"],
        ):
            sheet.write(row, 0, text, fmt["meta"])
            row += 1
        over = " / ".join(
            _("> %s วัน: %s (%s%%)") % (o["edge"], o["value"] if o["value"] is not None else o["qty"],
                                     o["pct_value"] if o["pct_value"] is not None else o["pct_qty"])
            for o in kpis["over"]
        )
        sheet.write(row, 0, _("KPI — อายุเฉลี่ย %s วัน · %s · สินค้าเสี่ยง %s จาก %s") % (
            kpis["avg_age"] if kpis["avg_age"] is not None else "-", over,
            kpis["risk"]["count"], kpis["risk"]["product_count"],
        ), fmt["meta"])
        row += 1
        if data["options"]["show_value"]:
            if checks["svl_scope_limited"]:
                sheet.write(row, 0, _(
                    "หมายเหตุ: รายงานถูกกรองคลัง/ที่เก็บ/ล็อต และชั้นมูลค่าสินค้า (SVL) "
                    "ไม่มีมิติเหล่านั้น จึงกระทบยอดกับมูลค่าทั้งบริษัทไม่ได้"
                ), fmt["meta"])
            else:
                style = fmt["meta_ok"] if checks["svl_reconciled"] else fmt["meta_warn"]
                sheet.write(row, 0, _(
                    "มูลค่าคงเหลือตามชั้นมูลค่าสินค้า (SVL): %s / ในรายงาน: %s / ผลต่าง: %s"
                ) % (checks["svl_value"], checks["report_value"], checks["svl_difference"]), style)
            row += 1
        if checks["unlayered_qty"]:
            sheet.write(row, 0, _(
                "คำเตือน: %s หน่วยหาวันรับเข้าไม่ได้ ถูกนับไว้ในช่วงเก่าสุด"
            ) % checks["unlayered_qty"], fmt["meta_warn"])
            row += 1
        return row + 1

    def _write_table_head(self, sheet, fmt, columns, head_row):
        for index, col in enumerate(columns):
            head = fmt["head_" + col["bucket"]] if col.get("bucket") else fmt["head"]
            if col["group"]:
                if col["group_span"]:
                    if col["group_span"] > 1:
                        sheet.merge_range(
                            head_row, index, head_row, index + col["group_span"] - 1,
                            col["group"], head,
                        )
                    else:
                        sheet.write(head_row, index, col["group"], head)
                sheet.write(head_row + 1, index, col["label"], head)
            else:
                sheet.merge_range(
                    head_row, index, head_row + 1, index, col["label"], head
                )
        return head_row + 2

    def _write_line(self, sheet, fmt, columns, row, line, data):
        kind = line["kind"]
        level = min(line.get("level") or 0, 7)
        shade = min(level, 2) if kind in ("group", "group_total") else None
        labels = data["status_labels"]
        for index, col in enumerate(columns):
            ctype = col["type"]
            value = line.get(col["key"])
            if ctype == "text":
                style = fmt["group_text_%s" % shade][0] if shade is not None else fmt["text"]
                sheet.write_string(row, index, line.get("code") or "", style)
            elif ctype == "name":
                style = (
                    fmt["group_text_%s" % shade][level] if shade is not None
                    else fmt["text_indent"][level]
                )
                sheet.write_string(row, index, line.get("name") or "", style)
            elif ctype == "uom":
                style = fmt["group_text_%s" % shade][0] if shade is not None else fmt["text"]
                sheet.write_string(row, index, line.get("uom_name") or "", style)
            elif ctype == "status":
                style = fmt["group_center_%s" % shade] if shade is not None else fmt["center"]
                sheet.write_string(row, index, labels.get(value, "") if value else "", style)
            else:
                style = (
                    fmt["group_%s_%s" % (ctype, shade)] if shade is not None else fmt[ctype]
                )
                if value is not None and value is not False and (value or ctype in ("days", "months")):
                    sheet.write_number(row, index, value, style)
                else:
                    sheet.write_blank(row, index, None, style)

    def _write_total(self, sheet, fmt, columns, data, row, first, last, helper_col):
        helper = xl_range(first, helper_col, last, helper_col)
        totals = data["totals"]
        for index, col in enumerate(columns):
            ctype = col["type"]
            if ctype in ("qty", "money") and col["additive"]:
                style = fmt["total_%s" % ctype]
                value_range = xl_range(first, index, last, index)
                sheet.write_formula(
                    row, index,
                    "=SUMPRODUCT(%s,%s)" % (helper, value_range),
                    style,
                    totals.get(col["key"]) or 0.0,
                )
            elif ctype == "name":
                sheet.write_string(row, index, totals["name"], fmt["total_text"])
            elif ctype in ("days", "months", "qty"):
                # ค่าที่บวกกันไม่ได้ — ใช้ตัวเลขที่เครื่องยนต์คำนวณให้ (หรือเว้นว่าง)
                value = totals.get(col["key"])
                if value is not None and value is not False:
                    sheet.write_number(row, index, value, fmt["total_%s" % ctype])
                else:
                    sheet.write_blank(row, index, None, fmt["total_%s" % ctype])
            elif ctype == "status":
                sheet.write_blank(row, index, None, fmt["total_center"])
            else:
                sheet.write_blank(row, index, None, fmt["total_text"])

    # ------------------------------------------------------------------
    def _sheet_buckets(self, workbook, fmt, data):
        """สรุปตามช่วงอายุ — ช่วง × จำนวน / มูลค่า / % ของทั้งหมด"""
        sheet = workbook.add_worksheet(_("สรุปตามช่วงอายุ"))
        sheet.set_column(0, 0, 22)
        sheet.set_column(1, 4, 16)
        totals = data["totals"]
        show_value = data["options"]["show_value"]
        sheet.write(0, 0, _("สรุปตามช่วงอายุ %s") % data["labels"]["as_of"], fmt["title"])
        head_row = 2
        heads = [_("ช่วงอายุ (วัน)"), _("จำนวน"), _("% จำนวน")]
        if show_value:
            heads += [_("มูลค่า"), _("% มูลค่า")]
        for index, head in enumerate(heads):
            sheet.write(head_row, index, head, fmt["head"])
        row = head_row + 1
        total_qty = totals["closing_qty"] or 0.0
        total_value = totals["closing_value"] or 0.0
        for spec in data["buckets"]:
            qty = totals.get(spec["key"] + "_qty") or 0.0
            sheet.write_string(row, 0, spec["label"], fmt["text"])
            sheet.write_number(row, 1, qty, fmt["qty"])
            sheet.write_number(row, 2, qty / total_qty * 100 if total_qty else 0.0, fmt["pct"])
            if show_value:
                value = totals.get(spec["key"] + "_value") or 0.0
                sheet.write_number(row, 3, value, fmt["money"])
                sheet.write_number(row, 4, value / total_value * 100 if total_value else 0.0, fmt["pct"])
            row += 1
        sheet.write_string(row, 0, totals["name"], fmt["total_text"])
        sheet.write_number(row, 1, total_qty, fmt["total_qty"])
        sheet.write_number(row, 2, 100.0 if total_qty else 0.0, fmt["total_qty"])
        if show_value:
            sheet.write_number(row, 3, total_value, fmt["total_money"])
            sheet.write_number(row, 4, 100.0 if total_value else 0.0, fmt["total_money"])
        row += 2
        kpis = data["kpis"]
        sheet.write(row, 0, _("อายุเฉลี่ย (วัน)"), fmt["text"])
        if kpis["avg_age"] is not None:
            sheet.write_number(row, 1, kpis["avg_age"], fmt["days"])
        row += 1
        for over in kpis["over"]:
            sheet.write(row, 0, _("เกิน %s วัน") % over["edge"], fmt["text"])
            sheet.write_number(row, 1, over["qty"] or 0.0, fmt["qty"])
            sheet.write_number(row, 2, over["pct_qty"] or 0.0, fmt["pct"])
            if show_value:
                sheet.write_number(row, 3, over["value"] or 0.0, fmt["money"])
                sheet.write_number(row, 4, over["pct_value"] or 0.0, fmt["pct"])
            row += 1
        sheet.write(row, 0, _("สินค้าเสี่ยง (Non-Moving / Obsolete)"), fmt["text"])
        sheet.write_number(row, 1, kpis["risk"]["count"], fmt["days"])
        sheet.write(row, 2, _("จาก %s สินค้า") % kpis["risk"]["product_count"], fmt["text"])

    # ------------------------------------------------------------------
    def _sheet_notes(self, workbook, fmt, data):
        sheet = workbook.add_worksheet(_("ข้อสังเกต"))
        sheet.set_column(0, 0, 34)
        sheet.set_column(1, 1, 80)
        checks = data["checks"]
        labels = data["labels"]
        sheet.write(0, 0, _("ข้อสังเกตของรายงานฉบับนี้"), fmt["title"])

        rows = [
            (_("จำนวนกลุ่มในรายงาน"), str(checks["group_count"])),
            (_("หลักการนับอายุ"), _(
                "%s — นับที่ระดับ %s (ของที่เหลือคือของที่รับเข้าล่าสุด การโอนเข้าคลัง/ที่เก็บ/ล็อต"
                "ใหม่นับเป็นการรับเข้าใหม่ของโหนดนั้น)"
            ) % (labels["age_basis"], checks["age_granularity"])),
            (_("การใช้เฉลี่ยต่อเดือน"), _(
                "%s — นับเฉพาะที่ออกจากบริษัท (ขาย/ผลิต) ไม่นับโอนภายใน ปรับปรุงยอด ของเสีย"
            ) % labels["usage_window"]),
            (_("เกณฑ์สถานะ"), labels["thresholds"]),
            (_("ตั้งค่าจากบริษัท"), checks["config_company"]),
        ]
        if data["options"]["show_value"]:
            if checks["svl_scope_limited"]:
                verdict = _("(กระทบยอดไม่ได้ เพราะรายงานถูกกรองคลัง/ที่เก็บ/ล็อต)")
            elif checks["svl_reconciled"]:
                verdict = _("(กระทบยอดได้)")
            else:
                verdict = _("(ไม่กระทบยอด!)")
            rows += [
                (_("มูลค่าคงเหลือตาม SVL"), "%s" % checks["svl_value"]),
                (_("มูลค่าคงเหลือตามรายงาน"), "%s" % checks["report_value"]),
                (_("ผลต่าง"), "%s %s" % (checks["svl_difference"], verdict)),
                (_("วิธีคิดมูลค่า"), labels["cost_basis"]),
            ]
            if checks["unbucketed_value"]:
                rows.append((_("มูลค่าที่ไม่ได้จัดช่วงอายุ"), _(
                    "%s (โหนดที่คงเหลือเป็นศูนย์หรือติดลบแต่ยังมีมูลค่า)"
                ) % checks["unbucketed_value"]))
        else:
            rows.append((_("มูลค่า"), _("ไม่แสดง — ผู้ใช้ไม่มีสิทธิ์ดูมูลค่าสินค้า")))
        if checks["unlayered_qty"]:
            rows.append((_("คำเตือน"), _(
                "%s หน่วยหาวันรับเข้าไม่ได้ (คงเหลือมากกว่ารายการรับเข้าทั้งประวัติ) "
                "ถูกนับไว้ในช่วงเก่าสุด"
            ) % checks["unlayered_qty"]))
        if checks["bucket_qty_difference"]:
            rows.append((_("หมายเหตุ"), _(
                "ยอดคงเหลือติดลบ %s หน่วย ไม่ถูกจัดเข้าช่วงอายุ"
            ) % checks["bucket_qty_difference"]))
        if checks["no_move_estimated_rows"]:
            rows.append((_("หมายเหตุ"), _(
                "%s แถวไม่เคยมีการจ่ายออก — วันไม่เคลื่อนไหวนับจากวันรับเข้าเก่าสุดแทน"
            ) % checks["no_move_estimated_rows"]))
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
