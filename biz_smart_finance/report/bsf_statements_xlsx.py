# -*- coding: utf-8 -*-
"""ส่งออกงบการเงิน + ศูนย์ต้นทุนเป็น Excel

กติกา (ยืมจาก biz_ac_trial_balance แล้วรัดให้แน่นกว่าเดิม):

* **ยอดรวมทุกช่องเป็นสูตร Excel จริง ไม่ใช่ค่าตายตัว** — ผู้สอบบัญชีกดดูที่มา
  ได้ทันที และถ้าใครแก้ตัวเลขแถวย่อย ยอดรวมจะขยับตาม โครงงบเป็นลำดับชั้น
  (section → group → account) จึงใช้ SUM ซ้อนตรง ๆ ไม่ต้องใช้คอลัมน์ช่วย
  ส่วนบรรทัดที่เป็น "ผลต่างข้ามหมวด" (กำไรขั้นต้น/สุทธิ, Available) เขียนเป็น
  สูตรอ้างเซลล์หมวดจริง จึงตรวจสอบย้อนได้ทั้งแผ่น
* เขียนค่าที่คำนวณไว้แล้วเป็น cached value ของ write_formula เสมอ (อาร์กิวเมนต์
  ที่ 5) — โปรแกรมที่ไม่ recalculate เช่น preview บนมือถือจะยังเห็นเลขถูก
* ฟอนต์ตั้งเป็น Sarabun เฉย ๆ (xlsx ฝังฟอนต์ไม่ได้) — เครื่องที่ไม่มีฟอนต์
  Excel จะ substitute ให้เอง ไม่ทำให้ไฟล์เสีย
"""
import io

from odoo import _, api, models
from odoo.tools.misc import xlsxwriter

# คีย์ถังอายุลูกหนี้ (ป้ายชื่อแปลตอนใช้งาน ไม่ใช่ตอน import)
AGING_KEYS = ["current", "b1_30", "b31_60", "b60_plus"]


class BsfStatementsXlsx(models.AbstractModel):
    _name = "biz.smart.finance.statements.xlsx"
    _description = "Smart Finance Statements XLSX Builder"

    @api.model
    def generate(self, filters=None):
        """คืน bytes ของไฟล์ xlsx (gate สิทธิ์อยู่ใน get_dashboard_data)"""
        payload = self.env["biz.smart.finance.dashboard"].get_dashboard_data(
            filters or {})
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
        fmt = self._formats(workbook)
        self._sheet_pnl(workbook, fmt, payload)
        self._sheet_balance(workbook, fmt, payload)
        self._sheet_cashflow(workbook, fmt, payload)
        self._sheet_aging(workbook, fmt, payload)
        self._sheet_compare(workbook, fmt, payload)
        self._sheet_controlling(workbook, fmt, payload)
        self._sheet_forecast(workbook, fmt, payload)
        workbook.close()
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # styles
    # ------------------------------------------------------------------
    def _formats(self, workbook):
        base = {"font_name": "Sarabun", "font_size": 10}
        num = "#,##0.00"
        return {
            "title": workbook.add_format(
                {**base, "font_size": 15, "bold": True}),
            "meta": workbook.add_format(
                {**base, "font_size": 9, "font_color": "#555555"}),
            "head": workbook.add_format({
                **base, "bold": True, "align": "center", "valign": "vcenter",
                "bg_color": "#F2F4F7", "border": 1, "text_wrap": True,
            }),
            "text": workbook.add_format({**base, "border": 1}),
            # indent ต้องสร้างล่วงหน้าทีละระดับ — format ของ xlsxwriter
            # แก้หลังสร้างไม่ได้
            "indent": [
                workbook.add_format({**base, "border": 1, "indent": level})
                for level in range(4)
            ],
            "num": workbook.add_format({**base, "border": 1, "num_format": num}),
            "pct": workbook.add_format(
                {**base, "border": 1, "num_format": '0.0"%"'}),
            "section": workbook.add_format(
                {**base, "bold": True, "border": 1, "bg_color": "#EAECF0"}),
            "section_num": workbook.add_format({
                **base, "bold": True, "border": 1, "bg_color": "#EAECF0",
                "num_format": num,
            }),
            "total": workbook.add_format({
                **base, "bold": True, "border": 1, "top": 6,
                "bg_color": "#D1E9FF",
            }),
            "total_num": workbook.add_format({
                **base, "bold": True, "border": 1, "top": 6,
                "bg_color": "#D1E9FF", "num_format": num,
            }),
            "total_pct": workbook.add_format({
                **base, "bold": True, "border": 1, "top": 6,
                "bg_color": "#D1E9FF", "num_format": '0.0"%"',
            }),
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _meta_lines(self, payload):
        echo = payload["filters"]
        lines = [
            _("บริษัท: %s") % echo["company_label"],
            _("ปีงบ: %s · ข้อมูลถึง %s (เทียบ %s)") % (
                echo["fy_label"], echo["as_of"], echo["as_of_prior"]),
            _("สกุลเงินนำเสนอ: %s") % echo["currency"],
        ]
        if echo["multi_currency"]:
            lines.append(_(
                "กลุ่มมีหลายสกุลเงิน — แปลงด้วยอัตราปิด ณ วันสิ้นงวดของแต่ละ"
                "คอลัมน์ ผลต่างอัตราไม่ได้แยกเป็นบรรทัดต่างหาก"))
        if echo["period_closed"]:
            lines.append(_("งวดนี้ปิดแล้ว (ล็อกถึง %s)") % echo["lock_date"])
        lines.append(_("พิมพ์โดย %s เมื่อ %s") % (
            self.env.user.name, payload["updated_at"]))
        return lines

    def _open_sheet(self, workbook, fmt, payload, name, title, widths):
        sheet = workbook.add_worksheet(name)
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        for index, width in enumerate(widths):
            sheet.set_column(index, index, width)
        sheet.write(0, 0, title, fmt["title"])
        row = 1
        for line in self._meta_lines(payload):
            sheet.write(row, 0, line, fmt["meta"])
            row += 1
        return sheet, row + 1

    def _write_header(self, sheet, fmt, row, labels):
        for index, label in enumerate(labels):
            sheet.write(row, index, label, fmt["head"])
        return row + 1

    def _sum_formula(self, sheet, fmt, row, column, rows, value, style):
        """ยอดรวม = SUM ของแถวลูกที่ระบุ (คืนค่า cached ไว้ด้วยเสมอ)

        แถวหมวดในงบแสดงฐานะการเงิน **ไม่ติดกัน** (แต่ละกลุ่มมีแถวรายบัญชีคั่น)
        ถ้าใช้ช่วง A5:A20 จะรวมแถวรายบัญชีซ้ำเข้าไปด้วย — ต้องเช็คความต่อเนื่อง
        ก่อนเสมอ แล้วบวกทีละเซลล์เมื่อไม่ต่อเนื่อง
        """
        if not rows:
            sheet.write_number(row, column, value or 0.0, style)
            return
        letter = xl_col(column)
        if rows[-1] - rows[0] == len(rows) - 1:
            formula = "=SUM(%s%d:%s%d)" % (
                letter, rows[0] + 1, letter, rows[-1] + 1)
        else:
            formula = "=" + "+".join(xl_cell(child, column) for child in rows)
        sheet.write_formula(row, column, formula, style, value or 0.0)

    # ------------------------------------------------------------------
    # sheets
    # ------------------------------------------------------------------
    def _sheet_pnl(self, workbook, fmt, payload):
        st = payload["statements"]
        sheet, row = self._open_sheet(
            workbook, fmt, payload, _("งบกำไรขาดทุน"),
            _("งบกำไรขาดทุน (Profit & Loss)"), [46, 18, 18, 18, 12])
        head_row = row
        row = self._write_header(sheet, fmt, row, [
            _("รายการ"), _("งวดนี้"), _("งวดก่อน"), _("ผลต่าง"), _("%"),
        ])
        # งบ waterfall: บรรทัด line = ยอดของถัง engine (คลุมบัญชีที่ map หลายที่
        # เช่น SG&A เป็นตัวปิด) + รายบัญชีขยายไว้ใต้บรรทัดเป็นข้อมูลประกอบ  บรรทัด
        # total = บรรทัดสรุปอ่านจาก engine ตรง ๆ  ยอดทั้งสองชนิดเขียนเป็นค่า —
        # สูตรข้ามเซลล์ของ waterfall (มี plug) ตรวจย้อนยากกว่าที่คุ้ม
        for line in st["pnl"]["rows"]:
            is_total = line["kind"] == "total"
            label_fmt = fmt["total"] if is_total else fmt["section"]
            num_fmt = fmt["total_num"] if is_total else fmt["section_num"]
            label = line["label"]
            if line.get("configured") is False:
                label = "%s  (ยังไม่ได้ผูกบัญชี)" % label
            sheet.write(row, 0, label, label_fmt)
            sheet.write_number(row, 1, line["amount"], num_fmt)
            sheet.write_number(row, 2, line["prior"], num_fmt)
            sheet.write_formula(
                row, 3, "=B%d-C%d" % (row + 1, row + 1),
                num_fmt, line["delta"])
            if line.get("pct_of_revenue") is not None:
                sheet.write_number(
                    row, 4, line["pct_of_revenue"], fmt["total_pct"])
            row += 1
            for account in line.get("accounts", ()):
                sheet.write(
                    row, 0, "%s %s" % (account["code"], account["label"]),
                    fmt["indent"][1])
                sheet.write_number(row, 1, account["amount"], fmt["num"])
                sheet.write_number(row, 2, account["prior"], fmt["num"])
                sheet.write_formula(
                    row, 3, "=B%d-C%d" % (row + 1, row + 1),
                    fmt["num"], account["delta"])
                row += 1
        sheet.freeze_panes(head_row + 1, 1)
        sheet.repeat_rows(head_row, head_row)

    def _sheet_balance(self, workbook, fmt, payload):
        bs = payload["statements"]["balance_sheet"]
        sheet, row = self._open_sheet(
            workbook, fmt, payload, _("งบแสดงฐานะการเงิน"),
            _("งบแสดงฐานะการเงิน (Balance Sheet)"), [50, 18, 18, 12])
        head_row = row
        row = self._write_header(sheet, fmt, row, [
            _("รายการ"), _("งวดนี้"), _("งวดก่อน"), _("%"),
        ])
        # โครง waterfall: บรรทัด line = ยอดของบรรทัดนั้น + กางรายบัญชีใต้บรรทัด
        # บรรทัด subtotal = สูตรผลรวมของบรรทัด line ในหมวด (หรือของ subtotal อื่น)
        # sec ของ subtotal (assets/liab/liab_eq) รวมจาก key ที่ SEC_SUBTOTALS ระบุ
        sec_line_rows = {}       # sec → [row index ของบรรทัด line]
        subtotal_rows = {}       # key → row index
        SEC_SUBTOTALS = {
            "total_ca": ("lines", "ca"), "total_nca": ("lines", "nca"),
            "total_assets": ("sum", ("total_ca", "total_nca")),
            "total_cl": ("lines", "cl"), "total_ncl": ("lines", "ncl"),
            "total_liab": ("sum", ("total_cl", "total_ncl")),
            "total_equity": ("lines", "eq"),
            "total_liab_eq": ("sum", ("total_liab", "total_equity")),
        }
        for line in bs["rows"]:
            if line["kind"] == "subtotal":
                sheet.write(row, 0, line["label"], fmt["total"])
                spec = SEC_SUBTOTALS.get(line["key"])
                for column in (1, 2):
                    child_rows = []
                    if spec and spec[0] == "lines":
                        child_rows = sec_line_rows.get(spec[1], [])
                    elif spec and spec[0] == "sum":
                        child_rows = [subtotal_rows[k] for k in spec[1]
                                      if k in subtotal_rows]
                    self._sum_formula(
                        sheet, fmt, row, column, child_rows,
                        line["amount"] if column == 1 else line["prior"],
                        fmt["total_num"])
                sheet.write_formula(
                    row, 3, "=B%d-C%d" % (row + 1, row + 1),
                    fmt["total_num"], line["delta"])
                subtotal_rows[line["key"]] = row
                row += 1
                continue
            label = line["label"]
            if line.get("configured") is False:
                label = "%s  (ยังไม่ได้ผูกบัญชี)" % label
            sheet.write(row, 0, label, fmt["indent"][1])
            sheet.write_number(row, 1, line["amount"], fmt["num"])
            sheet.write_number(row, 2, line["prior"], fmt["num"])
            sheet.write_formula(
                row, 3, "=B%d-C%d" % (row + 1, row + 1),
                fmt["num"], line["delta"])
            sec_line_rows.setdefault(line.get("sec"), []).append(row)
            row += 1
            for account in line.get("accounts", ()):
                sheet.write(
                    row, 0,
                    "%s %s" % (account["code"], account["label"]),
                    fmt["indent"][2])
                sheet.write_number(row, 1, account["amount"], fmt["num"])
                sheet.write_number(row, 2, account["prior"], fmt["num"])
                row += 1

        # บรรทัดพิสูจน์การดุล — สูตรจริง: รวมสินทรัพย์ − รวมหนี้สินและส่วนของผู้ถือหุ้น
        ta = subtotal_rows.get("total_assets")
        tle = subtotal_rows.get("total_liab_eq")
        sheet.write(
            row, 0, _("ผลต่าง (รวมสินทรัพย์ − รวมหนี้สินและส่วนของผู้ถือหุ้น)"),
            fmt["total"])
        if None not in (ta, tle):
            for column in (1, 2):
                sheet.write_formula(
                    row, column, "=%s-%s" % (
                        xl_cell(ta, column), xl_cell(tle, column)),
                    fmt["total_num"],
                    bs["check"] if column == 1 else 0.0)
        sheet.freeze_panes(head_row + 1, 1)
        sheet.repeat_rows(head_row, head_row)

    def _sheet_cashflow(self, workbook, fmt, payload):
        cf = payload["statements"]["cashflow"]
        sheet, row = self._open_sheet(
            workbook, fmt, payload, _("งบกระแสเงินสด"),
            _("งบกระแสเงินสด (ทางอ้อม)"), [56, 18, 18])
        head_row = row
        row = self._write_header(
            sheet, fmt, row, [_("รายการ"), _("งวดนี้"), _("งวดก่อน")])
        # waterfall: line = ยอดบรรทัด, subtotal (CFO/CFI/CFF) = สูตรผลรวมบรรทัด
        # line ในหมวด, net_change = สูตรผลรวม 3 subtotal
        CF_SUB = {
            "total_cfo": ("lines", "cfo"), "total_cfi": ("lines", "cfi"),
            "total_cff": ("lines", "cff"),
            "net_change": ("sum", ("total_cfo", "total_cfi", "total_cff")),
        }
        sec_line_rows = {}
        subtotal_rows = {}
        net_row = None
        for line in cf["rows"]:
            if line["kind"] == "subtotal":
                sheet.write(row, 0, line["label"], fmt["total"])
                spec = CF_SUB.get(line["key"])
                for column, key in ((1, "amount"), (2, "prior")):
                    if spec and spec[0] == "lines":
                        child = sec_line_rows.get(spec[1], [])
                    elif spec:
                        child = [subtotal_rows[k] for k in spec[1]
                                 if k in subtotal_rows]
                    else:
                        child = []
                    self._sum_formula(
                        sheet, fmt, row, column, child, line[key],
                        fmt["total_num"])
                subtotal_rows[line["key"]] = row
                if line["key"] == "net_change":
                    net_row = row
                row += 1
                continue
            label = line["label"]
            if line.get("configured") is False:
                label = "%s  (ยังไม่ได้ผูกบัญชี)" % label
            sheet.write(row, 0, label, fmt["indent"][1])
            sheet.write_number(row, 1, line["amount"], fmt["num"])
            sheet.write_number(row, 2, line["prior"], fmt["num"])
            sec_line_rows.setdefault(line.get("sec"), []).append(row)
            row += 1

        sheet.write(row, 0, _("เงินสดต้นงวด"), fmt["text"])
        sheet.write_number(row, 1, cf["opening_cash"], fmt["num"])
        opening_row = row
        row += 1
        sheet.write(row, 0, _("ผลต่างที่อธิบายไม่ได้ (บัญชีนอกโครงงบ)"), fmt["text"])
        sheet.write_number(row, 1, cf["check"], fmt["num"])
        check_row = row
        row += 1
        sheet.write(row, 0, _("เงินสดปลายงวด"), fmt["total"])
        sheet.write_formula(
            row, 1, "=%s+%s+%s" % (
                xl_cell(opening_row, 1), xl_cell(net_row, 1),
                xl_cell(check_row, 1)),
            fmt["total_num"], cf["closing_cash"])
        sheet.freeze_panes(head_row + 1, 1)

    def _sheet_aging(self, workbook, fmt, payload):
        aging = payload["statements"]["ar_aging"]
        sheet, row = self._open_sheet(
            workbook, fmt, payload, _("อายุลูกหนี้"),
            _("อายุลูกหนี้ (AR Aging)"), [40, 16, 16, 16, 16, 18])
        labels = [_("Current"), _("1 - 30 วัน"), _("31 - 60 วัน"),
                  _("เกิน 60 วัน")]
        head_row = row
        row = self._write_header(
            sheet, fmt, row, [_("ลูกค้า")] + labels + [_("รวม")])
        first = row
        for customer in aging["customers"]:
            sheet.write(row, 0, customer["name"], fmt["text"])
            for index, key in enumerate(AGING_KEYS):
                sheet.write_number(row, index + 1, customer[key], fmt["num"])
            sheet.write_formula(
                row, 5, "=SUM(B%d:E%d)" % (row + 1, row + 1),
                fmt["num"], customer["total"])
            row += 1
        last = row - 1
        sheet.write(row, 0, _("รวมลูกหนี้ที่แสดง"), fmt["total"])
        for index, key in enumerate(AGING_KEYS):
            column = index + 1
            letter = xl_col(column)
            if last >= first:
                sheet.write_formula(
                    row, column,
                    "=SUM(%s%d:%s%d)" % (letter, first + 1, letter, last + 1),
                    fmt["total_num"],
                    sum(c[key] for c in aging["customers"]))
            else:
                sheet.write_number(row, column, 0.0, fmt["total_num"])
        sheet.write_formula(
            row, 5, "=SUM(B%d:E%d)" % (row + 1, row + 1), fmt["total_num"],
            sum(c["total"] for c in aging["customers"]))
        row += 2
        sheet.write(row, 0, _("ยอดลูกหนี้คงค้างทั้งหมด"), fmt["text"])
        sheet.write_number(row, 1, aging["total"], fmt["num"])
        row += 1
        sheet.write(row, 0, _("ค้างเกินกำหนด"), fmt["text"])
        sheet.write_number(row, 1, aging["overdue"], fmt["num"])
        sheet.write_number(row, 2, aging["overdue_pct"], fmt["pct"])
        sheet.freeze_panes(head_row + 1, 1)

    def _sheet_compare(self, workbook, fmt, payload):
        """เปรียบเทียบหลายงวด — หนึ่งคอลัมน์ต่อหนึ่งช่วง (ข้ามถ้าปิดอยู่)

        งบกำไรขาดทุนเป็น waterfall: บรรทัด line (รายได้/ต้นทุน/SG&A/รายได้อื่น/
        ค่าเสื่อม/ดอกเบี้ย/ภาษี) เขียนเป็นค่า  บรรทัดสรุปทุกชั้นเขียนเป็นสูตร
        อ้างเซลล์บรรทัดเหนือมัน (กำไรขั้นต้น = รายได้−ต้นทุน, EBITDA = กำไรขั้นต้น
        −SG&A+รายได้อื่น, ฯลฯ) อัตราส่วนกันหารศูนย์ในสูตร ยอดสะสมงบดุลเป็นค่า
        """
        compare = payload.get("compare") or {}
        if not compare.get("enabled") or not compare.get("columns"):
            return
        columns = compare["columns"]
        sheet, row = self._open_sheet(
            workbook, fmt, payload, _("เปรียบเทียบ"),
            _("เปรียบเทียบหลายงวด (%s ช่วง)") % len(columns),
            [40] + [17] * len(columns))
        head_row = row
        row = self._write_header(
            sheet, fmt, row,
            [_("รายการ")] + ["%s\n%s" % (c["label"], c["sub"]) for c in columns])

        value_rows = {}

        def write_rows(rows, style, num_style):
            nonlocal row
            for line in rows:
                label = line["label"]
                if line.get("configured") is False:
                    label = "%s  (ยังไม่ได้ผูกบัญชี)" % label
                sheet.write(row, 0, label, style)
                for index in range(len(columns)):
                    sheet.write_number(
                        row, index + 1, line["values"][index], num_style)
                value_rows[line["key"]] = row
                row += 1

        def cell(key, column):
            return xl_cell(value_rows[key], column)

        # กำไรสรุปทุกชั้น = สูตรผลต่างของบรรทัดจริง (เรียงตาม waterfall จึงอ้าง
        # เฉพาะบรรทัดที่เขียนไปแล้ว)  SG&A เป็นบรรทัด line เขียนค่า จึงยังอ้างได้
        subtotal_makers = {
            "gross_op": lambda col: "=%s-%s" % (
                cell("revenue_op", col), cell("cogs", col)),
            "ebitda": lambda col: "=%s-%s+%s" % (
                cell("gross_op", col), cell("sga", col),
                cell("other_income", col)),
            "ebit": lambda col: "=%s-%s" % (
                cell("ebitda", col), cell("depreciation", col)),
            "pretax": lambda col: "=%s-%s" % (
                cell("ebit", col), cell("interest", col)),
            "net": lambda col: "=%s-%s" % (
                cell("pretax", col), cell("tax", col)),
        }

        sheet.write(row, 0, _("งบกำไรขาดทุน"), fmt["section"])
        row += 1
        for line in compare["pnl_rows"]:
            maker = subtotal_makers.get(line["key"])
            if maker:
                sheet.write(row, 0, line["label"], fmt["total"])
                for index in range(len(columns)):
                    sheet.write_formula(
                        row, index + 1, maker(index + 1),
                        fmt["total_num"], line["values"][index])
                value_rows[line["key"]] = row
                row += 1
            else:
                write_rows([line], fmt["indent"][1], fmt["num"])

        sheet.write(row, 0, _("ฐานะการเงิน (ยอดสะสม ณ สิ้นงวด)"), fmt["section"])
        row += 1
        for line in compare["bs_rows"]:
            is_tot = line["kind"] == "subtotal"
            write_rows(
                [line],
                fmt["total"] if is_tot else fmt["indent"][1],
                fmt["total_num"] if is_tot else fmt["num"])

        sheet.write(
            row, 0, _("งบกระแสเงินสด (กระแสในงวด)"), fmt["section"])
        row += 1
        for line in compare.get("cf_rows", []):
            is_tot = line["kind"] == "subtotal"
            write_rows(
                [line],
                fmt["total"] if is_tot else fmt["indent"][1],
                fmt["total_num"] if is_tot else fmt["num"])

        sheet.write(row, 0, _("อัตราส่วน"), fmt["section"])
        row += 1
        # อัตรากำไร = สูตรกันหารศูนย์บนรายได้จากการดำเนินงาน  การเติบโตของรายได้
        # = ผลต่างคอลัมน์ก่อนหน้า (ช่องแรกไม่มีฐานเทียบ → เว้นว่าง)
        margin_of = {"gp_pct": "gross_op", "ebitda_pct": "ebitda",
                     "net_pct": "net"}
        for line in compare["kpi_rows"]:
            sheet.write(row, 0, line["label"], fmt["text"])
            numerator = margin_of.get(line["key"])
            for index in range(len(columns)):
                column = index + 1
                value = line["values"][index]
                if numerator and "revenue_op" in value_rows:
                    sheet.write_formula(
                        row, column,
                        "=IF({rev}=0,\"\",{num}/{rev}*100)".format(
                            rev=cell("revenue_op", column),
                            num=cell(numerator, column)),
                        fmt["pct"], value if value is not None else 0.0)
                elif (line["key"] == "revenue_growth_pct"
                      and "revenue_op" in value_rows and index):
                    sheet.write_formula(
                        row, column,
                        "=IF({prev}=0,\"\",({cur}-{prev})/ABS({prev})*100)"
                        .format(cur=cell("revenue_op", column),
                                prev=cell("revenue_op", column - 1)),
                        fmt["pct"], value if value is not None else 0.0)
                elif value is None:
                    sheet.write(row, column, "", fmt["pct"])
                else:
                    sheet.write_number(row, column, value, fmt["pct"])
            row += 1
        sheet.freeze_panes(head_row + 1, 1)
        sheet.repeat_rows(head_row, head_row)

    def _sheet_controlling(self, workbook, fmt, payload):
        co = payload["controlling"]
        sheet, row = self._open_sheet(
            workbook, fmt, payload, _("ศูนย์ต้นทุน"),
            _("ศูนย์ต้นทุน (Controlling) — %s") % (co.get("plan_name") or "-"),
            [38, 16, 16, 16, 16, 12, 16, 16])
        if not co.get("configured"):
            sheet.write(row, 0, _("ยังไม่ได้ตั้งมิติวิเคราะห์"), fmt["meta"])
            return
        head_row = row
        row = self._write_header(sheet, fmt, row, [
            _("ศูนย์ต้นทุน"), _("งบประมาณ"), _("ใช้จริง"), _("ภาระผูกพัน"),
            _("คงเหลือ"), _("ใช้ไป %"), _("รายได้"), _("สุทธิ"),
        ])
        first = row
        for line in co["rows"]:
            name = ("%s %s" % (line["code"], line["name"])).strip()
            sheet.write(row, 0, name, fmt["text"])
            sheet.write_number(row, 1, line["budget"], fmt["num"])
            sheet.write_number(row, 2, line["actual_cost"], fmt["num"])
            sheet.write_number(row, 3, line["commitment"], fmt["num"])
            # คงเหลือ = งบ − ใช้จริง − ภาระผูกพัน (สูตรเดียวกับที่จอใช้)
            sheet.write_formula(
                row, 4, "=B{0}-C{0}-D{0}".format(row + 1), fmt["num"],
                line["available"])
            if line["utilization_pct"] is not None:
                sheet.write_formula(
                    row, 5, "=IF(B{0}=0,\"\",(C{0}+D{0})/B{0}*100)".format(
                        row + 1),
                    fmt["pct"], line["utilization_pct"])
            sheet.write_number(row, 6, line["actual_revenue"], fmt["num"])
            sheet.write_formula(
                row, 7, "=G{0}-C{0}".format(row + 1), fmt["num"],
                line["actual_net"])
            row += 1
        last = row - 1
        sheet.write(row, 0, _("รวม"), fmt["total"])
        totals = co["totals"]
        keys = {1: "budget", 2: "actual_cost", 3: "commitment",
                4: "available", 6: "actual_revenue", 7: "actual_net"}
        for column, key in keys.items():
            letter = xl_col(column)
            if last >= first:
                sheet.write_formula(
                    row, column,
                    "=SUM(%s%d:%s%d)" % (letter, first + 1, letter, last + 1),
                    fmt["total_num"], totals[key])
            else:
                sheet.write_number(row, column, totals[key], fmt["total_num"])
        if totals.get("utilization_pct") is not None:
            sheet.write_formula(
                row, 5, "=IF(B{0}=0,\"\",(C{0}+D{0})/B{0}*100)".format(row + 1),
                fmt["total_pct"], totals["utilization_pct"])
        sheet.freeze_panes(head_row + 1, 1)
        sheet.repeat_rows(head_row, head_row)

    def _sheet_forecast(self, workbook, fmt, payload):
        """พยากรณ์รายเดือน — เงินสด, กำไรขาดทุน, งานขาย, ต้นทุนคงเหลือ

        บรรทัดที่หาได้จากบรรทัดอื่น (สุทธิ, รวมรายได้/ต้นทุน, กำไร, อัตรากำไร)
        เขียนเป็นสูตรจริงตามกติกาของไฟล์นี้ ผู้ใช้จึงแก้สมมติฐานในชีตแล้วเห็น
        ผลกระทบทันทีโดยไม่ต้องกลับมาที่จอ
        """
        forecast = payload.get("forecast") or {}
        months = forecast.get("months") or []
        if not months:
            return
        cash = forecast["cash"]
        pnl = forecast["pnl"]
        columns = len(months)
        sheet, row = self._open_sheet(
            workbook, fmt, payload, _("พยากรณ์"),
            _("พยากรณ์รายเดือน (%s เดือน + หลังจากนี้)")
            % forecast.get("horizon_months"),
            [34] + [15] * columns + [16])
        head_row = row
        row = self._write_header(
            sheet, fmt, row,
            [_("รายการ")] + [m["label"] for m in months] + [_("รวม")])

        def series_row(label, values, style=None, num_style=None, total=True):
            nonlocal row
            sheet.write(row, 0, label, style or fmt["text"])
            for index in range(columns):
                sheet.write_number(
                    row, index + 1, (values or [0.0] * columns)[index] or 0.0,
                    num_style or fmt["num"])
            if total:
                sheet.write_formula(
                    row, columns + 1,
                    "=SUM(%s%d:%s%d)" % (
                        xl_col(1), row + 1, xl_col(columns), row + 1),
                    num_style or fmt["num"],
                    sum(values or []))
            written = row
            row += 1
            return written

        # ---- เงินสด ----
        sheet.write(row, 0, _("กระแสเงินสด"), fmt["section"])
        row += 1
        in_row = series_row(_("เงินเข้า"), cash["inflow"])
        out_row = series_row(_("เงินออก"), cash["outflow"])
        sheet.write(row, 0, _("กระแสเงินสดสุทธิ"), fmt["total"])
        for index in range(columns):
            letter = xl_col(index + 1)
            sheet.write_formula(
                row, index + 1,
                "=%s%d-%s%d" % (letter, in_row + 1, letter, out_row + 1),
                fmt["total_num"], cash["net"][index])
        row += 1
        series_row(_("เงินสดคงเหลือปลายเดือน"), cash["closing"],
                   fmt["total"], fmt["total_num"], total=False)
        if cash.get("has_min_cash"):
            sheet.write(row, 0, _("เงินสดขั้นต่ำ"), fmt["text"])
            for index in range(columns):
                sheet.write_number(
                    row, index + 1, cash["min_cash"], fmt["num"])
            row += 1
        row += 1

        # ---- กำไรขาดทุน ----
        sheet.write(row, 0, _("กำไรขาดทุนคาดการณ์"), fmt["section"])
        row += 1
        rev_backlog = series_row(_("รายได้ — งานที่เซ็นแล้ว"),
                                 pnl["revenue_backlog"])
        rev_pipeline = series_row(_("รายได้ — งานขาย (ถ่วงน้ำหนัก)"),
                                  pnl["revenue_pipeline"])
        rev_other = series_row(_("รายได้อื่น"), pnl["other_income"])
        rev_row = row
        sheet.write(row, 0, _("รวมรายได้"), fmt["section"])
        for index in range(columns):
            letter = xl_col(index + 1)
            sheet.write_formula(
                row, index + 1,
                "=%s%d+%s%d+%s%d" % (
                    letter, rev_backlog + 1, letter, rev_pipeline + 1,
                    letter, rev_other + 1),
                fmt["section_num"], pnl["revenue"][index])
        row += 1
        cost_project = series_row(_("ต้นทุนโครงการคงเหลือ"), pnl["cost_project"])
        cost_pipeline = series_row(_("ต้นทุนงานขาย (ถ่วงน้ำหนัก)"),
                                   pnl["cost_pipeline"])
        opex_row = series_row(_("ค่าใช้จ่ายประจำ"), pnl["opex"])
        cost_row = row
        sheet.write(row, 0, _("รวมต้นทุนและค่าใช้จ่าย"), fmt["section"])
        for index in range(columns):
            letter = xl_col(index + 1)
            sheet.write_formula(
                row, index + 1,
                "=%s%d+%s%d+%s%d" % (
                    letter, cost_project + 1, letter, cost_pipeline + 1,
                    letter, opex_row + 1),
                fmt["section_num"], pnl["cost"][index])
        row += 1
        margin_row = row
        sheet.write(row, 0, _("กำไรคาดการณ์"), fmt["total"])
        for index in range(columns):
            letter = xl_col(index + 1)
            sheet.write_formula(
                row, index + 1,
                "=%s%d-%s%d" % (letter, rev_row + 1, letter, cost_row + 1),
                fmt["total_num"], pnl["margin"][index])
        row += 1
        sheet.write(row, 0, _("อัตรากำไร (%)"), fmt["text"])
        for index in range(columns):
            letter = xl_col(index + 1)
            sheet.write_formula(
                row, index + 1,
                "=IF(%s%d=0,\"\",%s%d/%s%d*100)" % (
                    letter, rev_row + 1, letter, margin_row + 1,
                    letter, rev_row + 1),
                fmt["pct"], pnl["margin_pct"][index] or 0.0)
        row += 2

        # ---- งานขาย ----
        pipeline = forecast.get("pipeline") or {}
        if pipeline.get("rows"):
            sheet.write(row, 0, _("งานขายที่ยังไม่เซ็น"), fmt["section"])
            row += 1
            row = self._write_header(sheet, fmt, row, [
                _("ดีล"), _("คาดเซ็น"), _("ลูกค้า"), _("มูลค่า"), _("%"),
                _("ถ่วงน้ำหนัก"),
            ])
            for deal in pipeline["rows"]:
                sheet.write(row, 0, deal["name"], fmt["text"])
                sheet.write(row, 1, deal["sign_date"], fmt["text"])
                sheet.write(row, 2, deal["customer"], fmt["text"])
                sheet.write_number(row, 3, deal["amount"], fmt["num"])
                sheet.write_number(row, 4, deal["probability"], fmt["pct"])
                # ถ่วงน้ำหนัก = มูลค่า × ความน่าจะเป็น (สูตรจริง แก้ % แล้วเห็นผล)
                sheet.write_formula(
                    row, 5, "=D{0}*E{0}/100".format(row + 1), fmt["num"],
                    deal["weighted"])
                row += 1
            row += 1

        # ---- ต้นทุนคงเหลือ ----
        ctc = forecast.get("ctc") or {}
        if ctc.get("rows"):
            sheet.write(row, 0, _("ต้นทุนคงเหลือต่อโครงการ"), fmt["section"])
            row += 1
            row = self._write_header(sheet, fmt, row, [
                _("โครงการ"), _("EAC"), _("ใช้ไปแล้ว"), _("คงเหลือ"),
                _("กำหนดจบ"),
            ])
            for line in ctc["rows"]:
                sheet.write(row, 0, line["name"], fmt["text"])
                sheet.write_number(row, 1, line["eac"], fmt["num"])
                sheet.write_number(row, 2, line["cost_to_date"], fmt["num"])
                sheet.write_number(
                    row, 3, line["cost_to_complete"], fmt["num"])
                sheet.write(row, 4, line["end_date"] or "-", fmt["text"])
                row += 1

        sheet.freeze_panes(head_row + 1, 1)
        sheet.repeat_rows(head_row, head_row)


def xl_col(index):
    """0 → A, 25 → Z, 26 → AA"""
    letters = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters


def xl_cell(row, column):
    return "%s%d" % (xl_col(column), row + 1)
