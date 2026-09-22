import re
from odoo import models


class BomExcelReport(models.AbstractModel):
    _name = "report.buz_mrp_bom_excel_report.bom_excel_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "BOM Excel Report"

    def _text(self, value):
        return value or ""

    def _product_parts(self, product):
        if not product:
            return "", ""
        template = product.product_tmpl_id
        code = self._text(product.default_code or template.default_code)
        name = self._text(product.name or template.name)
        match = re.match(r"^\[([^\]]+)\]\s*(.*)$", name)
        if match:
            embedded_code, clean_name = match.groups()
            if not code:
                code = embedded_code
            name = clean_name
        return code, name

    def _product_code(self, product):
        """Return only the product code, including a bracketed-name fallback."""
        return self._product_parts(product)[0]

    def _product_name(self, product):
        """Return only the product name without a bracketed code prefix."""
        return self._product_parts(product)[1]

    def _bom_type(self, bom):
        if not bom:
            return ""
        field = bom._fields["type"]
        selection = dict(field._description_selection(self.env))
        return selection.get(bom.type, self._text(bom.type))

    def _parent_product(self, bom):
        return bom.product_id or bom.product_tmpl_id.product_variant_id

    def _get_boms(self, records=None):
        """Use selected BOMs or search all accessible BOMs without sudo."""
        boms = records.exists() if records is not None else self.env["mrp.bom"].search([])
        return boms.sorted(
            key=lambda bom: (
                self._product_code(self._parent_product(bom)),
                self._product_name(self._parent_product(bom)),
                self._text(bom.code or bom.display_name),
                bom.id,
            )
        )

    def _prepare_rows(self, boms):
        rows = []
        for bom in boms:
            parent = self._parent_product(bom)
            parent_values = {
                "product_code": self._product_code(parent),
                "product_name": self._product_name(parent),
                "bom_name": self._text(bom.code),
                # ฟิลด์ note อาจไม่มีใน mrp.bom ของบางระบบ จึงใช้ค่าว่างแทน
                # ฟิลด์ note อาจไม่มีใน mrp.bom ของบางระบบ จึงใช้ค่าว่างแทน
                "note": self._text(getattr(bom, "note", "")),
                "bom_type": self._bom_type(bom),
            }
            lines = bom.bom_line_ids.sorted(key=lambda line: line.sequence)
            if not lines:
                rows.append({
                    **parent_values,
                    "component_code": "",
                    "component_name": "",
                    "quantity": None,
                    "uom": "",
                })
                continue

            for line_index, line in enumerate(lines):
                component = line.product_id
                rows.append({
                    **parent_values,
                    **({} if line_index == 0 else {
                        "product_code": "",
                        "product_name": "",
                        "bom_name": "",
                    }),
                    "component_code": self._product_code(component),
                    "component_name": self._product_name(component),
                    "quantity": line.product_qty,
                    "uom": self._text(line.product_uom_id.name),
                })
        return rows

    def generate_xlsx_report(self, workbook, data, records):
        del data
        selected_boms = records if records and records._name == "mrp.bom" else None
        rows = self._prepare_rows(self._get_boms(selected_boms))

        title_format = workbook.add_format({
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "font_name": "TH Sarabun New",
            "font_size": 16,
            "border": 1,
        })
        header_format = workbook.add_format({
            "bold": True,
            "align": "center",
            "valign": "vcenter",
            "text_wrap": True,
            "font_name": "TH Sarabun New",
            "font_size": 12,
            "border": 1,
            "bg_color": "#D9EAF7",
        })
        text_format = workbook.add_format({
            "font_name": "TH Sarabun New",
            "font_size": 12,
            "valign": "top",
            "text_wrap": True,
            "border": 1,
        })
        center_format = workbook.add_format({
            "font_name": "TH Sarabun New",
            "font_size": 12,
            "valign": "top",
            "align": "center",
            "border": 1,
        })
        number_format = workbook.add_format({
            "font_name": "TH Sarabun New",
            "font_size": 12,
            "valign": "top",
            "align": "right",
            "num_format": "#,##0.00",
            "border": 1,
        })

        columns = [
            ("รหัสสินค้า", 18, "product_code", text_format),
            ("ชื่อสินค้า", 34, "product_name", text_format),
            ("ชื่อสูตร", 20, "bom_name", text_format),
            ("หมายเหตุ", 28, "note", text_format),
            ("รหัสสินค้ารายการ", 20, "component_code", text_format),
            ("รายการชื่อสินค้า", 38, "component_name", text_format),
            ("จำนวน", 12, "quantity", number_format),
            ("หน่วย", 12, "uom", center_format),
            ("ประเภท", 16, "bom_type", center_format),
        ]

        sheet = workbook.add_worksheet("BOM Report")
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(1, 1)
        sheet.freeze_panes(2, 0)
        sheet.set_row(0, 28)
        sheet.set_row(1, 24)

        for index, (_label, width, _key, _format) in enumerate(columns):
            sheet.set_column(index, index, width)

        last_col = len(columns) - 1
        sheet.merge_range(0, 0, 0, last_col, "รายงาน Bills of Materials", title_format)
        for col, (label, _width, _key, _format) in enumerate(columns):
            sheet.write(1, col, label, header_format)

        for row_index, row in enumerate(rows, start=2):
            for col, (_label, _width, key, cell_format) in enumerate(columns):
                value = row.get(key)
                if key == "quantity" and value is not None:
                    sheet.write_number(row_index, col, value, cell_format)
                else:
                    sheet.write(row_index, col, value or "", cell_format)

        if not rows:
            sheet.merge_range(2, 0, 2, last_col, "ไม่พบข้อมูล BOM", center_format)
