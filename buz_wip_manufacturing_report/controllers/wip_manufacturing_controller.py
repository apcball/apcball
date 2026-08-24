import io
import json
import logging

import xlsxwriter

from odoo import fields, http
from odoo.http import content_disposition, request

_logger = logging.getLogger(__name__)


class WipManufacturingController(http.Controller):

    @http.route("/wip_manufacturing_report/export_xlsx", type="http", auth="user", methods=["GET"])
    def export_wip_manufacturing_xlsx(self, **kw):
        try:
            date_from = fields.Date.from_string(kw["date_from"])
            date_to = fields.Date.from_string(kw["date_to"])
            status_list = [s for s in (kw.get("status_list") or "").split(",") if s]
            cost_source = kw.get("cost_source") or "svl"
            show_valuation_detail = kw.get("show_valuation_detail") in ("1", "true", "True")
            company_id = kw.get("company_id")
            company_ids = [int(company_id)] if company_id else None

            def _ids(name):
                raw = kw.get(name)
                return [int(x) for x in raw.split(",") if x] if raw else None

            engine = request.env["buz.wip.manufacturing.report"]
            data = engine.get_wip_data(
                mo_ids=_ids("mo_ids"),
                date_from=date_from,
                date_to=date_to,
                product_ids=_ids("product_ids"),
                component_ids=_ids("component_ids"),
                location_ids=_ids("location_ids"),
                status_list=status_list or None,
                show_valuation_detail=show_valuation_detail,
                cost_source=cost_source,
                company_ids=company_ids,
                page_size=0,
                page=0,
            )

            output = io.BytesIO()
            workbook = xlsxwriter.Workbook(output, {"in_memory": True})
            self._write_wip_sheet(workbook, data, date_from, date_to)
            workbook.close()
            output.seek(0)

            filename = "WIP_Manufacturing_Report_%s_%s.xlsx" % (date_from, date_to)
            response = request.make_response(
                output.getvalue(),
                headers=[
                    ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                    ("Content-Disposition", content_disposition(filename)),
                ],
            )
            return response
        except Exception as exc:  # noqa: BLE001
            _logger.exception("WIP Manufacturing Report export failed")
            error = {"message": "ไม่สามารถ Export ข้อมูลได้ กรุณาลองใหม่อีกครั้ง", "detail": str(exc)}
            return request.make_response(
                json.dumps(error), headers=[("Content-Type", "application/json")], status=400
            )

    def _write_wip_sheet(self, workbook, data, date_from, date_to):
        sheet = workbook.add_worksheet("WIP Manufacturing")
        sheet.set_landscape()

        fmts = {
            "title": workbook.add_format({"bold": True, "font_size": 14}),
            "sub": workbook.add_format({"font_size": 10}),
            "header": workbook.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1}),
            "mo_row": workbook.add_format({"bold": True, "bg_color": "#EFEFEF", "border": 1}),
            "num": workbook.add_format({"num_format": "#,##0.00", "border": 1}),
            "num_bold": workbook.add_format({"num_format": "#,##0.00", "bold": True, "border": 1}),
            "text": workbook.add_format({"border": 1}),
            "total": workbook.add_format({"bold": True, "bg_color": "#FFE699", "border": 1, "num_format": "#,##0.00"}),
        }

        sheet.set_column("A:A", 16)  # MO No.
        sheet.set_column("B:B", 12)  # MO Date
        sheet.set_column("C:C", 6)   # Item
        sheet.set_column("D:D", 18)  # Product Code
        sheet.set_column("E:E", 30)  # Product Name
        sheet.set_column("F:F", 20)  # Store / Location
        sheet.set_column("G:G", 12)  # Quantity
        sheet.set_column("H:H", 8)   # UOM
        sheet.set_column("I:I", 14)  # Unit Cost
        sheet.set_column("J:J", 16)  # Amount
        sheet.set_column("K:K", 20)  # MRP Request No.

        row = 0
        sheet.merge_range(row, 0, row, 10, "WIP MANUFACTURING REPORT", fmts["title"])
        row += 1
        sheet.write(row, 0, f"Date From : {date_from}", fmts["sub"])
        sheet.write(row, 3, f"Date To : {date_to}", fmts["sub"])
        row += 1
        sheet.write(row, 0, f"Total MOs: {data['summary']['total_mos']}", fmts["sub"])
        sheet.write(row, 3, f"Total Items: {data['summary']['total_items']}", fmts["sub"])
        sheet.write(row, 6, f"Total Qty: {data['summary']['total_quantity']:,.2f}", fmts["sub"])
        sheet.write(row, 8, f"Total WIP Value: {data['summary']['total_wip_value']:,.2f}", fmts["sub"])
        row += 2

        header_row = row
        headers = [
            "MO No.", "MO Date", "Item", "Product Code", "Product Name",
            "Store / Location", "Quantity", "UOM", "Unit Cost", "Amount",
            "MRP Request No.",
        ]
        for col, label in enumerate(headers):
            sheet.write(header_row, col, label, fmts["header"])
        row += 1
        data_start_row = row

        for mo in data["data"]:
            sheet.merge_range(row, 0, row, 10, f"{mo['mo_name']}  ({mo['mo_date']})", fmts["mo_row"])
            row += 1
            for idx, material in enumerate(mo["materials"], start=1):
                sheet.write(row, 0, mo["mo_name"], fmts["text"])
                sheet.write(row, 1, mo["mo_date"], fmts["text"])
                sheet.write(row, 2, idx, fmts["text"])
                sheet.write(row, 3, material["product_code"], fmts["text"])
                sheet.write(row, 4, material["product_name"], fmts["text"])
                sheet.write(row, 5, material["location_name"], fmts["text"])
                sheet.write(row, 6, material["quantity"], fmts["num"])
                sheet.write(row, 7, material["uom"], fmts["text"])
                sheet.write(row, 8, material["unit_cost"], fmts["num"])
                sheet.write(row, 9, material["amount"], fmts["num"])
                sheet.write(row, 10, material["mrp_request_name"], fmts["text"])
                row += 1
            sheet.write(row, 5, "MO Total", fmts["num_bold"])
            sheet.write(row, 6, mo["subtotal_qty"], fmts["num_bold"])
            sheet.write(row, 9, mo["subtotal_amount"], fmts["num_bold"])
            row += 1

        sheet.write(row, 5, "GRAND TOTAL", fmts["total"])
        sheet.write(row, 6, data["grand_total"]["quantity"], fmts["total"])
        sheet.write(row, 9, data["grand_total"]["amount"], fmts["total"])
        final_row = row

        sheet.freeze_panes(data_start_row, 0)
        sheet.repeat_rows(header_row, header_row)
        sheet.print_area(0, 0, final_row, 10)
        sheet.autofilter(header_row, 0, final_row, 10)
