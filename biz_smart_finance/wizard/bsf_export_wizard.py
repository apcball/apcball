# -*- coding: utf-8 -*-
"""ตัวกลางส่งออกงบการเงินจากหน้า CFO Cockpit

หน้าจอ OWL ไม่เรียก builder โดยตรง แต่ส่ง filters ดิบมาที่ `action_export`
ซึ่งสร้าง wizard ชั่วคราวหนึ่งตัวแล้วเดินเส้นทางเดียวกับปุ่มในกล่องโต้ตอบ —
`ir.actions.report` ต้องการ docids บนโมเดลจริงจึงจะพิมพ์ได้
"""
import base64
import json

from odoo import _, api, fields, models


class BsfExportWizard(models.TransientModel):
    _name = "biz.smart.finance.export.wizard"
    _description = "Smart Finance Statements Export"

    # เก็บ filters ที่หน้าจอส่งมาแบบดิบ — engine เป็นคน normalize เองอยู่แล้ว
    filters_json = fields.Char(string="ตัวกรอง", default="{}")
    xlsx_file = fields.Binary(string="ไฟล์ Excel", readonly=True,
                              attachment=False)
    xlsx_filename = fields.Char(string="ชื่อไฟล์", readonly=True)

    def _get_filters(self):
        self.ensure_one()
        try:
            filters = json.loads(self.filters_json or "{}")
        except ValueError:
            filters = {}
        return filters if isinstance(filters, dict) else {}

    @api.model
    def action_export(self, filters=None, output="pdf"):
        """เรียกจากปุ่มบนหน้าจอ OWL

        ไม่ต้อง gate สิทธิ์ซ้ำที่นี่: ทั้งสองเส้นทางเรียก
        `get_dashboard_data` ซึ่ง raise AccessError ให้อยู่แล้ว และการ gate
        สองที่ด้วยกติกาคนละชุดคือต้นทางของบั๊กสิทธิ์
        """
        wizard = self.create({"filters_json": json.dumps(filters or {})})
        if output == "xlsx":
            return wizard.action_export_xlsx()
        return wizard.action_print_pdf()

    def action_export_xlsx(self):
        self.ensure_one()
        filters = self._get_filters()
        content = self.env["biz.smart.finance.statements.xlsx"].generate(
            filters)
        payload_filters = self.env[
            "biz.smart.finance.dashboard"]._normalize_filters(filters)
        self.write({
            "xlsx_file": base64.b64encode(content),
            "xlsx_filename": _("งบการเงิน_%s.xlsx") % payload_filters["as_of"],
        })
        return {
            "type": "ir.actions.act_url",
            "url": (
                "/web/content/?model=biz.smart.finance.export.wizard&id=%s"
                "&field=xlsx_file&filename_field=xlsx_filename&download=true"
                % self.id
            ),
            "target": "self",
        }

    def action_print_pdf(self):
        self.ensure_one()
        return self.env.ref(
            "biz_smart_finance.action_report_bsf_statements"
        ).report_action(self, data={"filters": self._get_filters()})
