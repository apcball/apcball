# -*- coding: utf-8 -*-
from odoo import fields, models

from odoo.addons.biz_smart_finance.models.bsf_ext_fact import (
    METRIC_KEYS,
    METRIC_KEY_SET,
)

# คอลัมน์ที่คาดหวังในไฟล์ (แถวแรกเป็น header ชื่อคอลัมน์ตามนี้ ตัวเล็ก):
#   kind        inventory | ratio_input
#   metric_key  key จาก METRIC_KEYS (แถว inventory เว้นได้ = inventory_value)
#   category    ชื่อหมวดสินค้า (เฉพาะแถว inventory)
#   amount      มูลค่า (สกุลเงินบริษัท) — คั่นหลักพันได้
#   qty         จำนวน (ทางเลือก เฉพาะ inventory)
FILE_COLUMNS = ["kind", "metric_key", "category", "amount", "qty"]


class BsfFactImport(models.TransientModel):
    _name = "biz.smart.finance.fact.import"
    _inherit = ["biz.smart.finance.import.mixin"]
    _description = "Smart Finance — Import External Figures"

    date = fields.Date(
        string="วันสิ้นงวด", required=True,
        default=fields.Date.context_today,
        help="ตัวเลขทุกแถวในไฟล์ถือเป็น snapshot ณ วันนี้",
    )
    replace_existing = fields.Boolean(
        string="แทนที่ตัวเลขเดิมของงวดนี้", default=True,
        help="ลบแถวเดิมที่ (บริษัท, วันที่, ประเภท, metric, หมวด) ชนกันก่อนสร้างใหม่",
    )
    line_ids = fields.One2many(
        "biz.smart.finance.fact.import.line", "wizard_id",
        string="ตัวอย่างข้อมูล (แก้ไขได้)",
    )

    # ------------------------------------------------------------------
    # parse (ตัวอ่านไฟล์อยู่ใน biz.smart.finance.import.mixin)
    # ------------------------------------------------------------------
    def _file_columns(self):
        return FILE_COLUMNS

    # ------------------------------------------------------------------
    # actions
    # ------------------------------------------------------------------
    _preview_fields = ("kind", "metric_key", "label", "amount", "qty")
    _preview_context_fields = ("date",)

    def _parse_rows(self, rows):
        result = []
        for row in rows:
            if row["kind"].lower() == "inventory" and not row["metric_key"]:
                row["metric_key"] = "inventory_value"
            result.append(self._parse_cells(row, {
                "kind": ("kind", lambda v: self._selection(v, ("inventory", "ratio_input"), "ratio_input")),
                "metric_key": ("metric_key", lambda v: self._selection(v, METRIC_KEY_SET)),
                "label": ("category", str.strip),
                "amount": ("amount", self._to_float),
                "qty": ("qty", self._to_float),
            }))
        return result

    def _row_error(self, values, context):
        from odoo.addons.biz_smart_finance.models.bsf_input_validation import fact_error
        error = "" if values["kind"] and values["metric_key"] else "ต้องระบุประเภทและ metric_key"
        key = (values["kind"], values["metric_key"], values["label"] or "")
        return error or fact_error(values), key, False

    def _import_records(self):
        Fact = self.env["biz.smart.finance.ext.fact"]
        for kind in ("inventory", "ratio_input"):
            rows = [
                {
                    "metric_key": line.metric_key,
                    "label": line.label,
                    "amount": line.amount,
                    "qty": line.qty,
                    "note": "import: %s" % (self.file_name or ""),
                }
                for line in self.line_ids
                if line.kind == kind
            ]
            Fact.upsert_facts(
                self.company_id, self.date, kind, rows,
                source="import", replace=self.replace_existing)
        action = self.env["ir.actions.actions"]._for_xml_id(
            "biz_smart_finance.action_bsf_ext_fact")
        action["domain"] = [
            ("company_id", "=", self.company_id.id),
            ("date", "=", self.date),
        ]
        return action


class BsfFactImportLine(models.TransientModel):
    _name = "biz.smart.finance.fact.import.line"
    _inherit = ["biz.smart.finance.import.line.mixin"]
    _description = "Smart Finance — Import Preview Line"
    _order = "row_index, id"

    wizard_id = fields.Many2one(
        "biz.smart.finance.fact.import", required=True, ondelete="cascade",
    )
    row_index = fields.Integer(string="แถวในไฟล์", readonly=True)
    kind = fields.Selection(
        [("inventory", "สินค้าคงเหลือ"), ("ratio_input", "ตัวเลขอัตราส่วน")],
    )
    metric_key = fields.Selection(METRIC_KEYS, string="Metric")
    label = fields.Char(string="หมวดสินค้า")
    amount = fields.Float(string="มูลค่า")
    qty = fields.Float(string="จำนวน")
