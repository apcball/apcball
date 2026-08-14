import io
import json
import re
from datetime import datetime

import xlsxwriter

from odoo import fields, http
from odoo.http import content_disposition, request


INVALID_SHEET_CHARS = re.compile(r"[\[\]:*?/\\]")


def _safe_sheet_name(name, used_names):
    name = INVALID_SHEET_CHARS.sub(" ", name or "Sheet")[:31] or "Sheet"
    base = name
    i = 2
    while name.lower() in used_names:
        suffix = f" ({i})"
        name = base[: 31 - len(suffix)] + suffix
        i += 1
    used_names.add(name.lower())
    return name


class StockCardController(http.Controller):

    @http.route("/stock_card/export_xlsx", type="http", auth="user", methods=["GET"])
    def export_stock_card_xlsx(self, **kw):
        try:
            product_id = int(kw["product_id"])
            date_from = fields.Date.from_string(kw["date_from"])
            date_to = fields.Date.from_string(kw["date_to"])
            show_movements_only = kw.get("show_movements_only") in ("1", "true", "True")
            company_id = kw.get("company_id")
            company_ids = [int(company_id)] if company_id else None

            engine = request.env["buz.stock.card.report"]
            product = request.env["product.product"].browse(product_id)

            location_ids_param = kw.get("location_ids")
            warehouse_ids_param = kw.get("warehouse_ids")
            sheets = []  # list of (label, scope_ids)
            if location_ids_param or warehouse_ids_param:
                loc_ids = [int(x) for x in location_ids_param.split(",") if x] if location_ids_param else []
                wh_ids = [int(x) for x in warehouse_ids_param.split(",") if x] if warehouse_ids_param else []
                for warehouse in request.env["stock.warehouse"].browse(wh_ids):
                    scope_ids = engine.resolve_multi_location_scope([], [warehouse.id])
                    sheets.append((warehouse.name, scope_ids))
                for location in request.env["stock.location"].browse(loc_ids):
                    scope_ids = engine.resolve_multi_location_scope([location.id], [])
                    sheets.append((location.display_name, scope_ids))
            else:
                location_id = int(kw["location_id"])
                include_children = kw.get("include_children") in ("1", "true", "True")
                scope_ids = engine.resolve_location_scope(location_id, include_children)
                location_label = request.env["stock.location"].browse(location_id).display_name
                sheets.append((location_label, scope_ids))

            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})

            fmts = {
                "title": workbook.add_format({"bold": True, "font_size": 12}),
                "header": workbook.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1}),
                "num": workbook.add_format({"num_format": "#,##0.00", "border": 1}),
                "date": workbook.add_format({"num_format": "dd/mm/yy hh:mm:ss", "border": 1}),
                "text": workbook.add_format({"border": 1}),
            }

            used_names = set()
            for location_label, scope_ids in sheets:
                data = engine.get_stock_card_data(
                    product_id, scope_ids, date_from, date_to,
                    page_size=0, page=0,
                    show_movements_only=show_movements_only,
                    company_ids=company_ids,
                )
                sheet_name = _safe_sheet_name(location_label, used_names)
                self._write_stock_card_sheet(
                    workbook, fmts, sheet_name, product, location_label, data, date_from, date_to,
                )

            workbook.close()
            output.seek(0)

            filename = "Stock_Card_%s_%s_%s.xlsx" % (
                product.default_code or product.id, date_from, date_to,
            )
            response = request.make_response(
                output.getvalue(),
                headers=[
                    ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                    ("Content-Disposition", content_disposition(filename)),
                ],
            )
            return response
        except Exception as exc:  # noqa: BLE001
            error = {"message": "ไม่สามารถ Export ข้อมูลได้ กรุณาลองใหม่อีกครั้ง", "detail": str(exc)}
            return request.make_response(
                json.dumps(error), headers=[("Content-Type", "application/json")], status=400
            )

    def _write_stock_card_sheet(self, workbook, fmts, sheet_name, product, location_label, data, date_from, date_to):
        sheet = workbook.add_worksheet(sheet_name)

        sheet.set_column("A:A", 8)
        sheet.set_column("B:B", 12)
        sheet.set_column("C:C", 22)
        sheet.set_column("D:D", 16)
        sheet.set_column("E:E", 20)
        sheet.set_column("F:I", 12)

        row = 0
        sheet.write(row, 0, "Stock Card", fmts["title"])
        row += 1
        sheet.write(row, 0, f"Product: {product.default_code or ''} {product.name}")
        row += 1
        sheet.write(row, 0, f"Location: {location_label}")
        row += 1
        sheet.write(row, 0, f"Date Range: {date_from} - {date_to}")
        row += 1
        sheet.write(row, 0, f"Opening Balance: {data['opening_balance']:.2f}")
        sheet.write(row, 2, f"Total Incoming: {data['total_in']:.2f}")
        sheet.write(row, 4, f"Total Outgoing: {data['total_out']:.2f}")
        sheet.write(row, 6, f"Closing Balance: {data['closing_balance']:.2f}")
        row += 2

        headers = ["ลำดับ", "วันที่", "เอกสาร", "เลขที่", "อ้างอิง",
                   "ยอดยกมา", "รับ", "จ่าย", "คงเหลือ"]
        for col, label in enumerate(headers):
            sheet.write(row, col, label, fmts["header"])
        row += 1

        sheet.write(row, 0, 1, fmts["text"])
        sheet.write(row, 5, data["opening_balance"], fmts["num"])
        sheet.write(row, 6, 0.0, fmts["num"])
        sheet.write(row, 7, 0.0, fmts["num"])
        sheet.write(row, 8, data["opening_balance"], fmts["num"])
        row += 1

        for line in data["lines"]:
            sheet.write(row, 0, line["seq"], fmts["text"])
            line_date = datetime.strptime(line["date"], "%d/%m/%y %H:%M:%S") if line["date"] else None
            if line_date:
                sheet.write_datetime(row, 1, line_date, fmts["date"])
            else:
                sheet.write(row, 1, "", fmts["date"])
            sheet.write(row, 2, line["doc_type"] or "", fmts["text"])
            sheet.write(row, 3, line["doc_number"] or "", fmts["text"])
            sheet.write(row, 4, line["reference"] or "", fmts["text"])
            sheet.write(row, 5, line["opening"], fmts["num"])
            sheet.write(row, 6, line["in"], fmts["num"])
            sheet.write(row, 7, line["out"], fmts["num"])
            sheet.write(row, 8, line["balance"], fmts["num"])
            row += 1
