# -*- coding: utf-8 -*-
"""เทสส่งออกงบการเงิน — xlsx อ่านกลับด้วย stdlib (image ไม่มี openpyxl)"""
import base64
import xml.etree.ElementTree as ElementTree
import zipfile
from io import BytesIO

from odoo.exceptions import AccessError
from odoo.tests.common import TransactionCase

SHEET_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sheet_formulas(book, sheet_name="sheet1.xml"):
    """คืน {cell_ref: formula} ของชีตที่ระบุ"""
    root = ElementTree.fromstring(book.read("xl/worksheets/%s" % sheet_name))
    formulas = {}
    for cell in root.iter("%sc" % SHEET_NS):
        node = cell.find("%sf" % SHEET_NS)
        if node is not None and node.text:
            formulas[cell.get("r")] = node.text
    return formulas


class TestBsfExport(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        Users = cls.env["res.users"]
        cls.viewer = Users.create({
            "name": "BSF Export Viewer", "login": "bsf_export_viewer",
            "groups_id": [(6, 0, [
                cls.env.ref("base.group_user").id,
                cls.env.ref("biz_smart_finance.group_bsf_user").id,
            ])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.plain_user = Users.create({
            "name": "BSF Export Outsider", "login": "bsf_export_outsider",
            "groups_id": [(6, 0, [cls.env.ref("base.group_user").id])],
            "company_id": cls.company.id,
            "company_ids": [(6, 0, [cls.company.id])],
        })
        cls.filters = {"company_id": cls.company.id}

    def _workbook(self, filters=None):
        content = self.env["biz.smart.finance.statements.xlsx"].generate(
            filters or self.filters)
        return zipfile.ZipFile(BytesIO(content))

    def _sheet_names(self, book):
        return [
            sheet.get("name")
            for sheet in ElementTree.fromstring(
                book.read("xl/workbook.xml")).iter("%ssheet" % SHEET_NS)
        ]

    def test_xlsx_sheets(self):
        """ปิดการเปรียบเทียบ = ไม่มีแผ่นเปรียบเทียบ (ไฟล์เดิมไม่เปลี่ยนรูป)"""
        self.assertEqual(self._sheet_names(self._workbook()), [
            "งบกำไรขาดทุน", "งบแสดงฐานะการเงิน", "งบกระแสเงินสด",
            "อายุลูกหนี้", "ศูนย์ต้นทุน", "พยากรณ์",
        ])

    def test_xlsx_forecast_sheet_uses_formulas(self):
        """แผ่นพยากรณ์: บรรทัดที่หาได้จากบรรทัดอื่นต้องเป็นสูตรจริง
        ผู้ใช้จึงแก้สมมติฐานในไฟล์แล้วเห็นผลทันที"""
        book = self._workbook()
        names = self._sheet_names(book)
        self.assertIn("พยากรณ์", names)
        formulas = list(sheet_formulas(
            book, "sheet%d.xml" % (names.index("พยากรณ์") + 1)).values())
        self.assertTrue(formulas, "แผ่นพยากรณ์ต้องมีสูตร")
        # กระแสเงินสดสุทธิ = เงินเข้า − เงินออก (อ้างเซลล์ ไม่ใช่ค่าตายตัว)
        self.assertTrue(
            any("-" in f and f.startswith("B") for f in formulas), formulas[:5])
        # อัตรากำไรต้องกันหารศูนย์แบบเดียวกับแผ่นอื่นในไฟล์นี้
        self.assertTrue(any(f.startswith("IF(") for f in formulas))

    def test_xlsx_compare_sheet(self):
        """เปิดโหมดเปรียบเทียบแล้วต้องได้แผ่นเพิ่ม + อัตราส่วนเป็นสูตรจริง"""
        filters = dict(self.filters, compare_mode="month", compare_count=3)
        book = self._workbook(filters)
        names = self._sheet_names(book)
        self.assertIn("เปรียบเทียบ", names)
        # แทรกก่อนศูนย์ต้นทุน — ลำดับแผ่นคือลำดับที่ผู้ใช้อ่าน
        self.assertEqual(names.index("เปรียบเทียบ") + 1,
                         names.index("ศูนย์ต้นทุน"))
        formulas = list(sheet_formulas(
            book, "sheet%d.xml" % (names.index("เปรียบเทียบ") + 1)).values())
        self.assertTrue(formulas, "แผ่นเปรียบเทียบต้องมีสูตร")
        # กำไรขั้นต้น/สุทธิ อ้างเซลล์รายได้-ต้นทุน ไม่ใช่ค่าตายตัว
        self.assertTrue(
            any(f.count("-") >= 1 and "IF(" not in f for f in formulas),
            "กำไรขั้นต้น/สุทธิต้องเป็นสูตรผลต่างของบรรทัดจริง")
        # อัตราส่วนต้องกันหารศูนย์ไว้ในสูตร ไม่ใช่คำนวณมาแล้วเขียนทับ
        self.assertTrue(
            any(f.startswith("IF(") and "/" in f for f in formulas),
            "อัตราส่วนต้องเป็นสูตรที่กันตัวหารเป็นศูนย์")

    def test_xlsx_totals_are_real_formulas(self):
        """ยอดรวมต้องเป็นสูตร ไม่ใช่ค่าตายตัว — ผู้สอบบัญชีต้องกดดูที่มาได้"""
        book = self._workbook()
        pnl = sheet_formulas(book, "sheet1.xml")
        self.assertTrue(pnl, "แผ่นงบกำไรขาดทุนต้องมีสูตรอย่างน้อยหนึ่งช่อง")
        # ผลต่างงวดต้องเป็น B−C เสมอ
        self.assertTrue(
            any(f.replace(" ", "").startswith("B") and "-C" in f
                for f in pnl.values()),
            "ต้องมีสูตรผลต่าง =Bn-Cn")
        balance = sheet_formulas(book, "sheet2.xml")
        self.assertTrue(
            any(f.startswith("SUM(") or "+" in f for f in balance.values()),
            "ยอดหมวดในงบแสดงฐานะต้องเป็นผลรวมของแถวลูก")

    def test_xlsx_balance_sheet_sums_skip_detail_rows(self):
        """subtotal งบดุล waterfall = สูตรผลรวมของบรรทัด line ในหมวด
        (บรรทัด line ไม่ติดกันเพราะมีรายบัญชีแทรก → ต้องบวกทีละเซลล์)"""
        payload = self.env["biz.smart.finance.dashboard"].get_dashboard_data(
            self.filters)
        bs_rows = payload["statements"]["balance_sheet"]["rows"]
        # ต้องมีหมวดที่มีบรรทัด line >= 2 บรรทัดและอย่างน้อยหนึ่งบรรทัดกางรายบัญชี
        by_sec = {}
        for r in bs_rows:
            if r["kind"] == "line":
                by_sec.setdefault(r["sec"], []).append(r)
        candidate = any(
            len(lines) > 1 and any(li["accounts"] for li in lines)
            for lines in by_sec.values())
        if not candidate:
            self.skipTest("ข้อมูลในดีบีนี้ไม่มีหมวดที่มีหลาย line พร้อมรายบัญชี")
        formulas = sheet_formulas(self._workbook(), "sheet2.xml")
        joined = [f for f in formulas.values() if "+" in f and "SUM" not in f]
        self.assertTrue(
            joined,
            "subtotal ที่มีหลาย line คั่นด้วยรายบัญชีต้องได้สูตรบวกทีละเซลล์")

    def test_wizard_export_actions(self):
        Wizard = self.env["biz.smart.finance.export.wizard"].with_user(
            self.viewer)
        action = Wizard.action_export(self.filters, "xlsx")
        self.assertEqual(action["type"], "ir.actions.act_url")
        wizard = Wizard.browse(
            int(action["url"].split("&id=")[1].split("&")[0]))
        self.assertTrue(wizard.xlsx_file)
        self.assertTrue(wizard.xlsx_filename.endswith(".xlsx"))
        # ไฟล์ที่เก็บต้องเป็น zip ของจริง (xlsx = zip)
        self.assertTrue(zipfile.is_zipfile(
            BytesIO(base64.b64decode(wizard.xlsx_file))))

        pdf_action = Wizard.action_export(self.filters, "pdf")
        self.assertEqual(pdf_action["type"], "ir.actions.report")

    def test_export_requires_group(self):
        """คนนอกกลุ่มต้องส่งออกไม่ได้ (gate อยู่ที่ engine เส้นเดียว)"""
        with self.assertRaises(AccessError):
            self.env["biz.smart.finance.export.wizard"].with_user(
                self.plain_user).action_export(self.filters, "xlsx")

    def test_pdf_html_renders_with_thai_font(self):
        """เรนเดอร์ HTML อย่างเดียว ไม่เรียก wkhtmltopdf (รันใน CI ได้)"""
        wizard = self.env["biz.smart.finance.export.wizard"].create(
            {"filters_json": "{}"})
        html = self.env["ir.actions.report"]._render_qweb_html(
            "biz_smart_finance.report_statements_doc", wizard.ids,
            data={"filters": self.filters},
        )[0].decode()
        self.assertIn("งบกำไรขาดทุน", html)
        self.assertIn("งบแสดงฐานะการเงิน", html)
        # ปิดเปรียบเทียบ = ไม่มีบล็อกนั้นใน PDF
        self.assertNotIn("เปรียบเทียบหลายงวด", html)
        # กับดักตัวจริง: single-quote ใน @font-face ทำให้ฟอนต์ไม่ถูกฝัง
        self.assertIn("font-family:Sarabun", html.replace(" ", ""))
        self.assertIn("data:font/truetype;base64,", html)
        self.assertNotIn("&#39;", html.split("</style>")[0])

    def test_pdf_html_includes_compare_when_enabled(self):
        wizard = self.env["biz.smart.finance.export.wizard"].create(
            {"filters_json": "{}"})
        filters = dict(self.filters, compare_mode="quarter", compare_count=3)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "biz_smart_finance.report_statements_doc", wizard.ids,
            data={"filters": filters},
        )[0].decode()
        self.assertIn("เปรียบเทียบหลายงวด", html)
        payload = self.env["biz.smart.finance.dashboard"].get_dashboard_data(
            filters)
        for column in payload["compare"]["columns"]:
            self.assertIn(column["label"], html)
