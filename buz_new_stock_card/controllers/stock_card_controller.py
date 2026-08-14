import io
import json
from datetime import datetime

import xlsxwriter

from odoo import fields, http
from odoo.http import content_disposition, request


class StockCardController(http.Controller):

    @http.route("/stock_card/export_xlsx", type="http", auth="user", methods=["GET"])
    def export_stock_card_xlsx(self, **kw):
        try:
            product_id = int(kw["product_id"])
            location_id = int(kw["location_id"])
            include_children = kw.get("include_children") in ("1", "true", "True")
            date_from = fields.Date.from_string(kw["date_from"])
            date_to = fields.Date.from_string(kw["date_to"])
            show_movements_only = kw.get("show_movements_only") in ("1", "true", "True")
            company_id = kw.get("company_id")
            company_ids = [int(company_id)] if company_id else None

            engine = request.env["buz.stock.card.report"]
            scope_ids = engine.resolve_location_scope(location_id, include_children)
            product = request.env["product.product"].browse(product_id)
            location = request.env["stock.location"].browse(location_id)

            data = engine.get_stock_card_data(
                product_id, scope_ids, date_from, date_to,
                page_size=0, page=0,
                show_movements_only=show_movements_only,
                company_ids=company_ids,
            )

            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            sheet = workbook.add_worksheet("Stock Card")

            title_fmt = workbook.add_format({"bold": True, "font_size": 12})
            header_fmt = workbook.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1})
            num_fmt = workbook.add_format({"num_format": "#,##0.00", "border": 1})
            date_fmt = workbook.add_format({"num_format": "dd/mm/yy hh:mm:ss", "border": 1})
            text_fmt = workbook.add_format({"border": 1})

            sheet.set_column("A:A", 8)
            sheet.set_column("B:B", 12)
            sheet.set_column("C:C", 22)
            sheet.set_column("D:D", 16)
            sheet.set_column("E:E", 20)
            sheet.set_column("F:I", 12)

            row = 0
            sheet.write(row, 0, "Stock Card", title_fmt)
            row += 1
            sheet.write(row, 0, f"Product: {product.default_code or ''} {product.name}")
            row += 1
            sheet.write(row, 0, f"Location: {location.display_name}")
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
                sheet.write(row, col, label, header_fmt)
            row += 1

            sheet.write(row, 0, 1, text_fmt)
            sheet.write(row, 5, data["opening_balance"], num_fmt)
            sheet.write(row, 6, 0.0, num_fmt)
            sheet.write(row, 7, 0.0, num_fmt)
            sheet.write(row, 8, data["opening_balance"], num_fmt)
            row += 1

            for line in data["lines"]:
                sheet.write(row, 0, line["seq"], text_fmt)
                line_date = datetime.strptime(line["date"], "%d/%m/%y %H:%M:%S") if line["date"] else None
                if line_date:
                    sheet.write_datetime(row, 1, line_date, date_fmt)
                else:
                    sheet.write(row, 1, "", date_fmt)
                sheet.write(row, 2, line["doc_type"] or "", text_fmt)
                sheet.write(row, 3, line["doc_number"] or "", text_fmt)
                sheet.write(row, 4, line["reference"] or "", text_fmt)
                sheet.write(row, 5, line["opening"], num_fmt)
                sheet.write(row, 6, line["in"], num_fmt)
                sheet.write(row, 7, line["out"], num_fmt)
                sheet.write(row, 8, line["balance"], num_fmt)
                row += 1

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
