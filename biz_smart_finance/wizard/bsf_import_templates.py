"""Downloadable, round-trippable examples; headers remain the public import format."""
import csv
import io

from odoo.addons.biz_smart_finance.models.bsf_ext_account import ACCOUNT_TYPES
from odoo.addons.biz_smart_finance.models.bsf_ext_fact import METRIC_KEYS

HELP = {
    "kind": "inventory = สินค้าคงเหลือ; ratio_input = ตัวเลขอัตราส่วน (ค่าเริ่มต้น)",
    "metric_key": "รหัสตัวเลขการเงินตามรายการตัวเลือก; inventory เว้นได้ = inventory_value",
    "category": "หมวดสินค้า เฉพาะ inventory", "amount": "มูลค่า/งบ สกุลเงินบริษัท",
    "qty": "จำนวนสินค้า (เว้นได้ = 0)", "doc_type": "ar = ลูกหนี้ (ค่าเริ่มต้น); ap = เจ้าหนี้",
    "number": "เลขที่เอกสาร ใช้จับคู่เมื่อนำเข้าซ้ำ", "partner": "ชื่อคู่ค้า ตรงชื่อเดียวในบริษัท/รายการร่วมจึงผูกให้",
    "date": "วันที่เอกสาร YYYY-MM-DD (ค.ศ.) หรือเซลล์วันที่ Excel",
    "date_due": "ครบกำหนด YYYY-MM-DD; เว้นได้ = ใช้วันที่เอกสารในการคำนวณ",
    "amount_total": "ยอดรวม สกุลเงินบริษัท; ใบลดหนี้ใส่ติดลบ",
    "amount_untaxed": "ยอดก่อนภาษี; เว้นว่าง/0 = ใช้ยอดรวมในการคำนวณ",
    "amount_residual": "ยอดค้าง เครื่องหมายเดียวกับยอดรวม; 0 = ปิดแล้ว",
    "analytic": "รหัสหรือชื่อศูนย์ต้นทุนของบริษัท/รายการร่วม ต้องมีอยู่จริง",
    "date_from": "วันเริ่มต้น YYYY-MM-DD (ค.ศ.)", "date_to": "วันสิ้นสุด YYYY-MM-DD (ค.ศ.)",
    "code": "รหัสบัญชี เก็บเป็นข้อความเพื่อรักษาเลขศูนย์นำหน้า",
    "name": "ชื่อบัญชี ใช้เมื่อสร้างบัญชีใหม่", "account_type": "จำเป็นสำหรับบัญชีใหม่ ดูรายการตัวเลือก",
    "opening": "ยอดยกมา (เดบิต − เครดิต); เว้นได้ = 0",
    "debit": "เดบิตระหว่างงวด", "credit": "เครดิตระหว่างงวด",
}


def build_template(wizard, extension):
    columns = wizard._file_columns()
    kind = wizard._name.split(".")[-2]
    if kind == "doc":
        kind = wizard.mode
    if kind == "fact":
        rows = [["inventory", "inventory_value", "สินค้าตัวอย่าง", 1000, 10],
                ["ratio_input", "total_assets", "", 5000, ""]]
    elif kind == "invoice":
        rows = [["ar", "EXAMPLE-001", "คู่ค้าตัวอย่าง", "2026-01-01", "2026-01-31", 1070, 1000, 1070]]
    elif kind == "budget":
        # Choose an existing unambiguous key so the downloaded example can be previewed directly.
        accounts = wizard.env["account.analytic.account"].search([
            "|", ("company_id", "=", False), ("company_id", "=", wizard.company_id.id)])
        keys = [value for account in accounts for value in (account.code, account.name) if value]
        resolved = wizard._analytic_map(keys)
        key = next((key for key in keys if resolved[key][0]), "ระบุรหัสศูนย์ต้นทุนที่มีอยู่")
        rows = [[key, "2026-01-01", "2026-01-31", 1000]]
    else:
        rows = [["001001", "เงินสดตัวอย่าง", "asset_cash", 0, 1000, 0],
                ["004001", "รายได้ตัวอย่าง", "income", 0, 0, 1000]]
    if extension == "csv":
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(columns)
        writer.writerows(rows)
        content = stream.getvalue().encode("utf-8-sig")
    else:
        import xlsxwriter
        stream = io.BytesIO()
        with xlsxwriter.Workbook(stream, {"in_memory": True, "strings_to_formulas": False,
                                          "strings_to_urls": False}) as workbook:
            sheet = workbook.add_worksheet("ข้อมูล")
            heading = workbook.add_format({"bold": True, "bg_color": "#DCEEF3"})
            text_format = workbook.add_format({"num_format": "@"})
            sheet.freeze_panes(1, 0)
            sheet.set_column(0, len(columns) - 1, 24)
            sheet.write_row(0, 0, columns, heading)
            for col, name in enumerate(columns):
                sheet.write_comment(0, col, HELP[name])
                if name in ("code", "number", "analytic"):
                    sheet.set_column(col, col, 26, text_format)
            for index, row in enumerate(rows, 1):
                sheet.write_row(index, 0, row)
            help_sheet = workbook.add_worksheet("คำแนะนำ")
            help_sheet.set_column(0, 0, 24)
            help_sheet.set_column(1, 1, 18)
            help_sheet.set_column(2, 2, 90)
            help_sheet.write_row(0, 0, ["คอลัมน์", "หัวคอลัมน์จำเป็น", "คำอธิบาย"], heading)
            for index, name in enumerate(columns, 1):
                help_sheet.write_row(index, 0, [name, "ใช่" if name in wizard._required_columns() else "ไม่", HELP[name]])
            start = len(columns) + 3
            help_sheet.write(start, 0, "แก้ข้อมูลตัวอย่างให้เป็นข้อมูลจริงก่อนนำเข้า")
            help_sheet.write(start + 1, 0, "วันที่ ค.ศ.; ยอดเงินสกุลเงินบริษัท; ใช้ค่าข้อมูลแทนสูตร")
            if kind in ("fact", "tb"):
                choices = METRIC_KEYS if kind == "fact" else ACCOUNT_TYPES
                for index, row in enumerate(choices, start + 3):
                    help_sheet.write_row(index, 0, row)
        content = stream.getvalue()
    return content, "smart_finance_%s.%s" % (kind, extension)
