# -*- coding: utf-8 -*-
"""นำเข้าเอกสารภายนอก: ใบแจ้งหนี้/บิลค้าง (AR/AP) และงบศูนย์ต้นทุน

คอลัมน์ที่คาดหวัง (แถวแรกเป็น header ชื่อคอลัมน์ตามนี้ ตัวพิมพ์เล็ก):

โหมด "ใบแจ้งหนี้/บิลค้าง"
    doc_type          ar | ap
    number            เลขที่เอกสารในระบบภายนอก (กุญแจตอน sync ซ้ำ)
    partner           ชื่อคู่ค้า — ถ้าตรงกับคู่ค้าใน Odoo แบบไม่กำกวมจะผูกให้
    date              วันที่เอกสาร (YYYY-MM-DD)
    date_due          วันครบกำหนด (เว้นได้ = ใช้วันที่เอกสาร)
    amount_total      ยอดรวม
    amount_untaxed    ยอดก่อนภาษี (เว้นได้ = ใช้ยอดรวม)
    amount_residual   ยอดค้าง

โหมด "งบศูนย์ต้นทุน"
    analytic          รหัสหรือชื่อศูนย์ต้นทุน (analytic account) — ต้องมีอยู่จริง
    date_from         ตั้งแต่วันที่
    date_to           ถึงวันที่
    amount            งบต้นทุนของทั้งช่วง

แถวที่ resolve ศูนย์ต้นทุนไม่ได้/กำกวม จะถูกทำเครื่องหมายเป็น error และ
**บล็อกการนำเข้าทั้งไฟล์** — ไม่มีการเดาให้ (กติกาเดียวกับ adapter API)
"""
from collections import defaultdict

from odoo import api, fields, models

from odoo.addons.biz_smart_finance.models.bsf_ext_invoice import DOC_TYPES

INVOICE_COLUMNS = [
    "doc_type", "number", "partner", "date", "date_due",
    "amount_total", "amount_untaxed", "amount_residual",
]
BUDGET_COLUMNS = ["analytic", "date_from", "date_to", "amount"]


class BsfDocImport(models.TransientModel):
    _name = "biz.smart.finance.doc.import"
    _inherit = ["biz.smart.finance.import.mixin"]
    _description = "Smart Finance — Import External Invoices / Budgets"

    mode = fields.Selection(
        [("invoice", "ใบแจ้งหนี้ / บิลค้าง (AR/AP)"),
         ("budget", "งบศูนย์ต้นทุน")],
        string="ชนิดข้อมูล", required=True, default="invoice",
    )
    replace_existing = fields.Boolean(
        string="แทนที่รายการเดิมที่ซ้ำกุญแจ", default=True,
        help="ใบแจ้งหนี้: (ประเภท, เลขที่) · งบ: (ศูนย์ต้นทุน, ช่วงวันที่)",
    )
    line_ids = fields.One2many(
        "biz.smart.finance.doc.import.line", "wizard_id",
        string="ตัวอย่างข้อมูล (แก้ไขได้)",
    )

    # ------------------------------------------------------------------
    # parse (ตัวอ่านไฟล์อยู่ใน biz.smart.finance.import.mixin)
    # ------------------------------------------------------------------
    def _file_columns(self):
        return BUDGET_COLUMNS if self.mode == "budget" else INVOICE_COLUMNS

    def _required_columns(self):
        if self.mode == "budget":
            return ["analytic", "date_from", "date_to", "amount"]
        return ["number", "date", "amount_total", "amount_residual"]

    @api.onchange("mode")
    def _onchange_mode(self):
        """เปลี่ยนชนิดข้อมูล = ไฟล์คนละรูปแบบ — ล้าง preview เดิมทิ้ง"""
        self.line_ids = [(5, 0, 0)]
        self.state = "draft"

    def _to_date(self, text):
        return fields.Date.to_date((text or "").strip() or None)

    def _partner_map(self, names):
        """{ชื่อ: partner_id} สำหรับชื่อที่ตรงตัวและไม่กำกวม

        กติกาเดิมของ `_resolve_partner` ทุกข้อ (ตรงตัว, เจอมากกว่าหนึ่ง = ข้าม)
        แต่ยิงคิวรีเดียวต่อไฟล์แทนหนึ่งคิวรีต่อแถว — ไฟล์ AR สองพันบรรทัดเคย
        เท่ากับสองพัน search บนคอลัมน์ name ที่ไม่มี index
        """
        wanted = sorted({(n or "").strip() for n in names if (n or "").strip()})
        if not wanted:
            return {}
        found = defaultdict(list)
        for row in self.env["res.partner"].search_read(
                [("name", "in", wanted),
                 "|", ("company_id", "=", False),
                 ("company_id", "=", self.company_id.id)], ["name"]):
            found[row["name"]].append(row["id"])
        return {name: ids[0] for name, ids in found.items() if len(ids) == 1}

    def _analytic_map(self, texts):
        """{ข้อความ: (analytic_id, warning)} — รหัสก่อนแล้วชื่อ เหมือนเดิมเป๊ะ"""
        wanted = sorted({(t or "").strip() for t in texts if (t or "").strip()})
        if not wanted:
            return {}
        Analytic = self.env["account.analytic.account"]
        by_code, by_name = defaultdict(list), defaultdict(list)
        for row in Analytic.search_read(
                [("code", "in", wanted), "|", ("company_id", "=", False),
                 ("company_id", "=", self.company_id.id)], ["code"]):
            by_code[row["code"]].append(row["id"])
        for row in Analytic.search_read(
                [("name", "in", wanted), "|", ("company_id", "=", False),
                 ("company_id", "=", self.company_id.id)], ["name"]):
            by_name[row["name"]].append(row["id"])
        result = {}
        for text in wanted:
            for bucket in (by_code, by_name):
                ids = bucket.get(text) or []
                if len(ids) == 1:
                    result[text] = (ids[0], "")
                    break
                if len(ids) > 1:
                    result[text] = (
                        False, "ศูนย์ต้นทุน '%s' ซ้ำหลายรายการ" % text)
                    break
            else:
                result[text] = (
                    False, "ไม่พบศูนย์ต้นทุน '%s' ใน Odoo" % text)
        return result

    def _resolve_partner(self, name):
        """ชื่อ → res.partner ถ้าตรงตัวและไม่กำกวม (ไม่ตรงก็ไม่เป็นไร)"""
        name = (name or "").strip()
        if not name:
            return False
        return self._partner_map([name]).get(name, False)

    def _resolve_analytic(self, text):
        """รหัสหรือชื่อ → account.analytic.account (ต้องเจอตัวเดียวเท่านั้น)"""
        text = (text or "").strip()
        if not text:
            return False, "ไม่ได้ระบุศูนย์ต้นทุน"
        return self._analytic_map([text]).get(
            text, (False, "ไม่พบศูนย์ต้นทุน '%s' ใน Odoo" % text))

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    _preview_fields = ("doc_type", "number", "partner_name", "partner_id", "date", "date_due",
                       "amount_total", "amount_untaxed", "amount_residual", "analytic_account_id",
                       "date_from", "date_to", "amount")
    _preview_context_fields = ("mode",)

    def _parse_rows(self, rows):
        result = []
        if self.mode == "invoice":
            partners = self._partner_map(row["partner"] for row in rows)
            mappings = {name: (name, self._to_float) for name in
                        ("amount_total", "amount_untaxed", "amount_residual")}
            mappings.update({name: (name, self._to_date) for name in ("date", "date_due")})
            mappings.update({"doc_type": ("doc_type", lambda v: self._selection(v, {c for c, _ in DOC_TYPES}, "ar")),
                             "number": ("number", str.strip), "partner_name": ("partner", str.strip)})
            for row in rows:
                values = self._parse_cells(row, mappings)
                values["partner_id"] = partners.get(row["partner"], False)
                result.append(values)
        else:
            accounts = self._analytic_map(row["analytic"] for row in rows)
            for row in rows:
                values = self._parse_cells(row, {
                    "date_from": ("date_from", self._to_date), "date_to": ("date_to", self._to_date),
                    "amount": ("amount", self._to_float)})
                account_id, error = accounts.get(row["analytic"], (False, "ไม่ได้ระบุศูนย์ต้นทุน"))
                values["analytic_account_id"] = account_id
                if error:
                    values["input_errors"]["analytic_account_id"] = error
                result.append(values)
        return result

    def _row_error(self, values, context):
        from odoo.addons.biz_smart_finance.models.bsf_input_validation import (
            invoice_error, budget_error, company_error)
        if self.mode == "invoice":
            error = "" if values["doc_type"] and values["number"] and values["date"] else "ต้องระบุประเภท เลขที่ และวันที่เอกสาร"
            error = error or invoice_error(values) or company_error(self.company_id, values["partner_id"], "คู่ค้า")
            key = (values["doc_type"], (values["number"] or "").strip())
        else:
            error = "" if values["analytic_account_id"] and values["date_from"] and values["date_to"] else "ต้องระบุศูนย์ต้นทุนและช่วงวันที่ให้ครบ"
            error = error or budget_error(values) or company_error(self.company_id, values["analytic_account_id"], "ศูนย์ต้นทุน")
            key = (values["analytic_account_id"].id, values["date_from"], values["date_to"])
        return error, key, False

    def _import_records(self):
        note = "import: %s" % (self.file_name or "")
        if self.mode == "budget":
            self.env["biz.smart.finance.ext.budget"].upsert_budgets(
                self.company_id,
                [
                    {
                        "analytic_account_id": line.analytic_account_id.id,
                        "date_from": line.date_from,
                        "date_to": line.date_to,
                        "amount": line.amount,
                        "note": note,
                    }
                    for line in self.line_ids
                ],
                source="import", replace=self.replace_existing)
            xml_id = "biz_smart_finance.action_bsf_ext_budget"
        else:
            self.env["biz.smart.finance.ext.invoice"].upsert_invoices(
                self.company_id,
                [
                    {
                        "doc_type": line.doc_type,
                        "number": line.number,
                        "partner_id": line.partner_id.id,
                        "partner_name": (
                            line.partner_name
                            or line.partner_id.display_name or "ไม่ระบุ"),
                        "date": line.date,
                        "date_due": line.date_due,
                        "amount_total": line.amount_total,
                        "amount_untaxed": line.amount_untaxed,
                        "amount_residual": line.amount_residual,
                        "note": note,
                    }
                    for line in self.line_ids
                ],
                source="import", replace=self.replace_existing)
            xml_id = "biz_smart_finance.action_bsf_ext_invoice"
        action = self.env["ir.actions.actions"]._for_xml_id(xml_id)
        action["domain"] = [("company_id", "=", self.company_id.id)]
        return action


class BsfDocImportLine(models.TransientModel):
    _name = "biz.smart.finance.doc.import.line"
    _inherit = ["biz.smart.finance.import.line.mixin"]
    _description = "Smart Finance — Import Preview Line (docs)"
    _order = "row_index, id"

    wizard_id = fields.Many2one(
        "biz.smart.finance.doc.import", required=True, ondelete="cascade",
    )
    row_index = fields.Integer(string="แถวในไฟล์", readonly=True)
    # ---- ใบแจ้งหนี้ ----
    doc_type = fields.Selection(DOC_TYPES, string="ประเภท")
    number = fields.Char(string="เลขที่")
    partner_name = fields.Char(string="คู่ค้า")
    partner_id = fields.Many2one("res.partner", string="คู่ค้าใน Odoo",
        domain="['|', ('company_id', '=', False), ('company_id', '=', parent.company_id)]")
    date = fields.Date(string="วันที่")
    date_due = fields.Date(string="ครบกำหนด")
    amount_total = fields.Float(string="ยอดรวม")
    amount_untaxed = fields.Float(string="ก่อนภาษี")
    amount_residual = fields.Float(string="ยอดค้าง")
    # ---- งบศูนย์ต้นทุน ----
    analytic_account_id = fields.Many2one(
        "account.analytic.account", string="ศูนย์ต้นทุน",
        domain="['|', ('company_id', '=', False), ('company_id', '=', parent.company_id)]",
    )
    date_from = fields.Date(string="ตั้งแต่")
    date_to = fields.Date(string="ถึง")
    amount = fields.Float(string="งบ")
    # ---- ผลตรวจ ----

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id and not self.partner_name:
            self.partner_name = self.partner_id.display_name
