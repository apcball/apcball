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
            date_from = fields.Date.from_string(kw["date_from"])
            date_to = fields.Date.from_string(kw["date_to"])
            show_movements_only = kw.get("show_movements_only") in ("1", "true", "True")
            can_see_value = request.env.user.has_group("buz_new_stock_card.group_stock_card_see_value")
            include_cost_lot = can_see_value and kw.get("include_cost_lot") in ("1", "true", "True")
            company_id = kw.get("company_id")
            company_ids = [int(company_id)] if company_id else None

            engine = request.env["buz.stock.card.report"]
            if company_ids:
                if not set(company_ids).issubset(request.env.user.company_ids.ids):
                    raise ValueError("บริษัทที่เลือกไม่อยู่ในบริษัทที่อนุญาต")
                engine = engine.with_context(allowed_company_ids=company_ids)

            product_id_param = kw.get("product_id")
            location_ids_param = kw.get("location_ids")
            warehouse_ids_param = kw.get("warehouse_ids")
            report_scope = kw.get("report_scope") == "1"

            if not report_scope and not product_id_param and not location_ids_param and not warehouse_ids_param:
                if include_cost_lot:
                    rows = engine.get_all_stock_card_valuation_lines(
                        date_from, date_to, company_ids=company_ids,
                    )
                    filename = "Stock_Card_Valuation_All_%s_%s.xlsx" % (date_from, date_to)
                    return self._flat_valuation_response(rows, filename, by_warehouse=True)
                rows = engine.get_all_stock_card_lines(
                    date_from, date_to,
                    company_ids=company_ids,
                    show_movements_only=show_movements_only,
                )
                filename = "Stock_Card_All_%s_%s.xlsx" % (date_from, date_to)
                return self._flat_sheet_response(rows, filename, by_warehouse=True)

            loc_ids = [int(x) for x in location_ids_param.split(",") if x] if location_ids_param else []
            wh_ids = [int(x) for x in warehouse_ids_param.split(",") if x] if warehouse_ids_param else []

            if not report_scope and product_id_param and not loc_ids and not wh_ids:
                product = request.env["product.product"].browse(int(product_id_param))
                if include_cost_lot:
                    rows = engine.get_product_all_locations_valuation_lines(
                        int(product_id_param), date_from, date_to, company_ids=company_ids,
                    )
                    filename = "Stock_Card_Valuation_%s_AllLoc_%s_%s.xlsx" % (
                        product.default_code or product.id, date_from, date_to,
                    )
                    return self._flat_valuation_response(rows, filename, by_warehouse=True)
                rows = engine.get_product_all_locations_lines(
                    int(product_id_param), date_from, date_to,
                    company_ids=company_ids,
                    show_movements_only=show_movements_only,
                )
                filename = "Stock_Card_%s_AllLoc_%s_%s.xlsx" % (
                    product.default_code or product.id, date_from, date_to,
                )
                return self._flat_sheet_response(rows, filename, by_warehouse=True)

            sheets = []  # list of (label, scope_ids)
            if report_scope:
                scope = engine.resolve_report_scope(
                    int(company_id), wh_ids, loc_ids, kw.get("include_children") == "1",
                )
                sheets.append((scope["label"], scope["location_ids"]))
            for warehouse in request.env["stock.warehouse"].browse([] if report_scope else wh_ids):
                scope_ids = engine.resolve_multi_location_scope([], [warehouse.id])
                sheets.append((warehouse.name, scope_ids))
            for location in request.env["stock.location"].browse([] if report_scope else loc_ids):
                scope_ids = engine.resolve_multi_location_scope([location.id], [])
                sheets.append((location.display_name, scope_ids))

            if not sheets:
                raise ValueError("ไม่พบคลังสินค้าหรือ Location ที่เลือก")

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

            if product_id_param and include_cost_lot:
                product_id = int(product_id_param)
                product = request.env["product.product"].browse(product_id)
                for location_label, scope_ids in sheets:
                    rows = engine.get_stock_card_valuation_lines(
                        product_id, scope_ids, date_from, date_to, company_ids=company_ids,
                    )
                    sheet_name = _safe_sheet_name(location_label, used_names)
                    self._write_valuation_sheet(workbook, fmts, rows, sheet_name=sheet_name, group_by_warehouse=True)
                filename = "Stock_Card_Valuation_%s_%s_%s.xlsx" % (
                    product.default_code or product.id, date_from, date_to,
                )
            elif product_id_param:
                product_id = int(product_id_param)
                product = request.env["product.product"].browse(product_id)
                for scope_label, scope_ids in sheets:
                    groups = engine.split_scope_by_warehouse(scope_ids)
                    for warehouse_name, group_ids in groups:
                        location_label = scope_label if len(groups) == 1 else "%s - %s" % (
                            scope_label, warehouse_name or "ไม่มีคลังสินค้า",
                        )
                        data = engine.get_stock_card_data(
                            product_id, group_ids, date_from, date_to,
                            page_size=0, page=0,
                            show_movements_only=show_movements_only,
                            company_ids=company_ids,
                        )
                        sheet_name = _safe_sheet_name(location_label, used_names)
                        self._write_stock_card_sheet(
                            workbook, fmts, sheet_name, product, location_label, data, date_from, date_to,
                        )
                filename = "Stock_Card_%s_%s_%s.xlsx" % (
                    product.default_code or product.id, date_from, date_to,
                )
            elif include_cost_lot:
                for location_label, scope_ids in sheets:
                    rows = engine.get_scoped_stock_card_valuation_lines(
                        scope_ids, date_from, date_to, company_ids=company_ids,
                    )
                    sheet_name = _safe_sheet_name(location_label, used_names)
                    self._write_valuation_sheet(workbook, fmts, rows, sheet_name=sheet_name, group_by_warehouse=True)
                filename = "Stock_Card_Valuation_ByScope_%s_%s.xlsx" % (date_from, date_to)
            else:
                for location_label, scope_ids in sheets:
                    rows = []
                    for warehouse_name, group_ids in engine.split_scope_by_warehouse(scope_ids):
                        group_rows = engine.get_scoped_stock_card_lines(
                            group_ids, date_from, date_to, scope_label=location_label,
                            company_ids=company_ids,
                            show_movements_only=show_movements_only,
                        )
                        for row in group_rows:
                            row["warehouse_name"] = warehouse_name
                        rows.extend(group_rows)
                    sheet_name = _safe_sheet_name(location_label, used_names)
                    self._write_all_stock_card_sheet(
                        workbook, fmts, rows, sheet_name=sheet_name, group_by_warehouse=True,
                    )
                filename = "Stock_Card_ByScope_%s_%s.xlsx" % (date_from, date_to)

            workbook.close()
            output.seek(0)

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

    @staticmethod
    def _group_rows_by_warehouse(rows):
        """[(warehouse_name, rows)] sorted by warehouse (rows without one go
        last); seq renumbered continuously across the whole sheet."""
        groups = {}
        for row in rows:
            groups.setdefault(row.get("warehouse_name") or "", []).append(row)
        ordered = sorted(groups.items(), key=lambda kv: (kv[0] == "", kv[0]))
        seq = 0
        result = []
        for name, group_rows in ordered:
            for row in group_rows:
                seq += 1
                row["seq"] = seq
            result.append((name or "ไม่มีคลังสินค้า", group_rows))
        return result

    @staticmethod
    def _closing_by_key(group_rows, key_fields, opening_field, balance_fields):
        """Sum, over each (location, product) key in the group, of the first
        row's opening and the last row's closing - rows are already ordered
        so the first/last row per key are its start and end."""
        first, last = {}, {}
        for row in group_rows:
            key = tuple(row[f] for f in key_fields)
            first.setdefault(key, row)
            last[key] = row
        opening = sum(r[opening_field] for r in first.values()) if opening_field else None
        closing = [sum(r[f] for r in last.values()) for f in balance_fields]
        return opening, closing

    @staticmethod
    def _add_group_formats(workbook, fmts):
        fmts["group"] = workbook.add_format({"bold": True, "bg_color": "#DDEBF7", "border": 1})
        fmts["subtotal"] = workbook.add_format({"bold": True, "bg_color": "#F2F2F2", "border": 1})
        fmts["subtotal_num"] = workbook.add_format(
            {"bold": True, "bg_color": "#F2F2F2", "border": 1, "num_format": "#,##0.00"}
        )

    def _flat_valuation_response(self, rows, filename, by_warehouse=False):
        """xlsx (cost+lot layout) from a flat valuation rows list; one sheet,
        or one sheet per warehouse when by_warehouse."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        fmts = {
            "header": workbook.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1}),
            "num": workbook.add_format({"num_format": "#,##0.00", "border": 1}),
            "date": workbook.add_format({"num_format": "dd/mm/yy hh:mm:ss", "border": 1}),
            "text": workbook.add_format({"border": 1}),
        }
        self._add_group_formats(workbook, fmts)
        self._write_valuation_sheet(workbook, fmts, rows, group_by_warehouse=by_warehouse)
        workbook.close()
        output.seek(0)
        return request.make_response(
            output.getvalue(),
            headers=[
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )

    def _write_valuation_sheet(self, workbook, fmts, rows, sheet_name="Stock Card", group_by_warehouse=False):
        sheet = workbook.add_worksheet(sheet_name)

        sheet.set_column("A:A", 8)
        sheet.set_column("B:B", 14)
        sheet.set_column("C:C", 28)
        sheet.set_column("D:D", 14)
        sheet.set_column("E:E", 10)
        sheet.set_column("F:F", 20)
        sheet.set_column("G:H", 18)
        sheet.set_column("I:I", 16)
        sheet.set_column("J:J", 14)
        sheet.set_column("K:M", 14)
        sheet.set_column("N:P", 14)
        sheet.set_column("Q:R", 16)
        sheet.set_column("S:T", 26)
        sheet.set_column("U:U", 18)

        headers = ["ลำดับ", "รหัสสินค้า", "ชื่อสินค้า", "Lot", "คลังสินค้า", "โลเคชั่น",
                   "ประเภทเอกสาร", "เลขที่เอกสาร", "วันที่",
                   "ยอดยกมา",
                   "จำนวนรับ", "ราคาต่อหน่วย(รับ)", "มูลค่ารับ",
                   "จำนวนจ่าย", "ราคาต่อหน่วย(จ่าย)", "มูลค่าจ่าย",
                   "ยอดคงเหลือ", "มูลค่าสินค้าคงเหลือ", "ต้นทาง", "ปลายทาง", "หมายเหตุ"]
        for col, label in enumerate(headers):
            sheet.write(0, col, label, fmts["header"])

        def write_line(row, line):
            sheet.write(row, 0, line["seq"], fmts["text"])
            sheet.write(row, 1, line["product_default_code"], fmts["text"])
            sheet.write(row, 2, line["product_name"], fmts["text"])
            sheet.write(row, 3, line["lot_name"] or "", fmts["text"])
            sheet.write(row, 4, line["warehouse_name"], fmts["text"])
            sheet.write(row, 5, line["location_label"], fmts["text"])
            sheet.write(row, 6, line["doc_type"] or "", fmts["text"])
            sheet.write(row, 7, line["doc_number"] or "", fmts["text"])
            line_date = datetime.strptime(line["date"], "%d/%m/%y %H:%M:%S") if line["date"] else None
            if line_date:
                sheet.write_datetime(row, 8, line_date, fmts["date"])
            else:
                sheet.write(row, 8, "", fmts["date"])
            sheet.write(row, 9, line["opening_qty"], fmts["num"])
            sheet.write(row, 10, line["qty_in"], fmts["num"])
            sheet.write(row, 11, line["unitcost_in"], fmts["num"])
            sheet.write(row, 12, line["cost_in"], fmts["num"])
            sheet.write(row, 13, line["qty_out"], fmts["num"])
            sheet.write(row, 14, line["unitcost_out"], fmts["num"])
            sheet.write(row, 15, line["cost_out"], fmts["num"])
            sheet.write(row, 16, line["balance_qty"], fmts["num"])
            sheet.write(row, 17, line["balance_value"], fmts["num"])
            sheet.write(row, 18, line["source_location"] or "", fmts["text"])
            sheet.write(row, 19, line["dest_location"] or "", fmts["text"])
            sheet.write(row, 20, line["remark"] or "", fmts["text"])

        row = 1
        if not group_by_warehouse or not rows:
            for line in rows:
                write_line(row, line)
                row += 1
            return
        key_fields = ("location_label", "product_default_code", "product_name")
        for name, group_rows in self._group_rows_by_warehouse(rows):
            sheet.merge_range(row, 0, row, 20, "คลังสินค้า: %s" % name, fmts["group"])
            row += 1
            for line in group_rows:
                write_line(row, line)
                row += 1
            _opening, (closing_qty, closing_value) = self._closing_by_key(
                group_rows, key_fields, None, ("balance_qty", "balance_value"),
            )
            sheet.merge_range(row, 0, row, 8, "รวม %s" % name, fmts["subtotal"])
            sheet.write(row, 9, "", fmts["subtotal"])
            sheet.write(row, 10, sum(r["qty_in"] for r in group_rows), fmts["subtotal_num"])
            sheet.write(row, 11, "", fmts["subtotal"])
            sheet.write(row, 12, sum(r["cost_in"] for r in group_rows), fmts["subtotal_num"])
            sheet.write(row, 13, sum(r["qty_out"] for r in group_rows), fmts["subtotal_num"])
            sheet.write(row, 14, "", fmts["subtotal"])
            sheet.write(row, 15, sum(r["cost_out"] for r in group_rows), fmts["subtotal_num"])
            sheet.write(row, 16, closing_qty, fmts["subtotal_num"])
            sheet.write(row, 17, closing_value, fmts["subtotal_num"])
            for blank_col in (18, 19, 20):
                sheet.write(row, blank_col, "", fmts["subtotal"])
            row += 1

    def _flat_sheet_response(self, rows, filename, by_warehouse=False):
        """xlsx (14-column 'All' layout) from a flat rows list; one sheet; with
        by_warehouse, rows get a header and a subtotal row per warehouse."""
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        fmts = {
            "header": workbook.add_format({"bold": True, "bg_color": "#D9D9D9", "border": 1}),
            "num": workbook.add_format({"num_format": "#,##0.00", "border": 1}),
            "date": workbook.add_format({"num_format": "dd/mm/yy hh:mm:ss", "border": 1}),
            "text": workbook.add_format({"border": 1}),
        }
        self._add_group_formats(workbook, fmts)
        self._write_all_stock_card_sheet(workbook, fmts, rows, group_by_warehouse=by_warehouse)
        workbook.close()
        output.seek(0)
        return request.make_response(
            output.getvalue(),
            headers=[
                ("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
                ("Content-Disposition", content_disposition(filename)),
            ],
        )

    def _write_all_stock_card_sheet(self, workbook, fmts, rows, sheet_name="Stock Card", group_by_warehouse=False):
        sheet = workbook.add_worksheet(sheet_name)
        show_value = bool(rows) and "value" in rows[0]

        sheet.set_column("A:A", 8)
        sheet.set_column("B:B", 20)
        sheet.set_column("C:C", 14)
        sheet.set_column("D:D", 28)
        sheet.set_column("E:E", 16)
        sheet.set_column("F:G", 16)
        sheet.set_column("H:K", 12)
        sheet.set_column("L:M", 26)
        sheet.set_column("N:N", 24)
        if show_value:
            sheet.set_column("O:O", 16)

        headers = ["ลำดับ", "คลังสินค้า", "รหัสสินค้า", "ชื่อสินค้า", "วันที่", "เอกสาร", "เลขที่",
                   "ยอดยกมา", "รับ", "จ่าย", "คงเหลือ", "ต้นทาง", "ปลายทาง", "หมายเหตุ"]
        if show_value:
            headers.append("มูลค่าสินค้า (บาท)")
        for col, label in enumerate(headers):
            sheet.write(0, col, label, fmts["header"])

        def write_line(row, line):
            sheet.write(row, 0, line["seq"], fmts["text"])
            sheet.write(row, 1, line["location_label"], fmts["text"])
            sheet.write(row, 2, line["product_default_code"], fmts["text"])
            sheet.write(row, 3, line["product_name"], fmts["text"])
            line_date = datetime.strptime(line["date"], "%d/%m/%y %H:%M:%S") if line["date"] else None
            if line_date:
                sheet.write_datetime(row, 4, line_date, fmts["date"])
            else:
                sheet.write(row, 4, "", fmts["date"])
            sheet.write(row, 5, line["doc_type"] or "", fmts["text"])
            sheet.write(row, 6, line["doc_number"] or "", fmts["text"])
            sheet.write(row, 7, line["opening"], fmts["num"])
            sheet.write(row, 8, line["in"], fmts["num"])
            sheet.write(row, 9, line["out"], fmts["num"])
            sheet.write(row, 10, line["balance"], fmts["num"])
            sheet.write(row, 11, line["from_location"] or "", fmts["text"])
            sheet.write(row, 12, line["to_location"] or "", fmts["text"])
            sheet.write(row, 13, line["note"] or "", fmts["text"])
            if show_value:
                sheet.write(row, 14, line.get("value", 0.0), fmts["num"])

        row = 1
        if not group_by_warehouse or not rows:
            for line in rows:
                write_line(row, line)
                row += 1
            return
        last_col = len(headers) - 1
        key_fields = ("location_label", "product_default_code", "product_name")
        for name, group_rows in self._group_rows_by_warehouse(rows):
            sheet.merge_range(row, 0, row, last_col, "คลังสินค้า: %s" % name, fmts["group"])
            row += 1
            for line in group_rows:
                write_line(row, line)
                row += 1
            opening, (closing, closing_value) = self._closing_by_key(
                group_rows, key_fields, "opening", ("balance", "value" if show_value else "balance"),
            )
            sheet.merge_range(row, 0, row, 6, "รวม %s" % name, fmts["subtotal"])
            sheet.write(row, 7, opening, fmts["subtotal_num"])
            sheet.write(row, 8, sum(r["in"] for r in group_rows), fmts["subtotal_num"])
            sheet.write(row, 9, sum(r["out"] for r in group_rows), fmts["subtotal_num"])
            sheet.write(row, 10, closing, fmts["subtotal_num"])
            for col in (11, 12, 13):
                sheet.write(row, col, "", fmts["subtotal"])
            if show_value:
                sheet.write(row, 14, closing_value, fmts["subtotal_num"])
            row += 1

    def _write_stock_card_sheet(self, workbook, fmts, sheet_name, product, location_label, data, date_from, date_to):
        sheet = workbook.add_worksheet(sheet_name)
        show_value = bool(data.get("can_see_value"))

        sheet.set_column("A:A", 8)
        sheet.set_column("B:B", 12)
        sheet.set_column("C:C", 22)
        sheet.set_column("D:D", 16)
        sheet.set_column("E:E", 20)
        sheet.set_column("F:G", 24)
        sheet.set_column("H:K", 12)
        if show_value:
            sheet.set_column("L:N", 16)

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
        if show_value:
            row += 1
            sheet.write(row, 0, f"Opening Value: {data['opening_value']:.2f}")
            sheet.write(row, 2, f"Total Incoming Value: {data['total_in_value']:.2f}")
            sheet.write(row, 4, f"Total Outgoing Value: {data['total_out_value']:.2f}")
            sheet.write(row, 6, f"Closing Value: {data['closing_value']:.2f}")
        row += 2

        headers = ["ลำดับ", "วันที่", "เอกสาร", "เลขที่", "อ้างอิง", "ต้นทาง", "ปลายทาง",
                   "ยอดยกมา", "รับ", "จ่าย", "คงเหลือ"]
        if show_value:
            headers.append("มูลค่าสินค้า (บาท)")
            headers.append("มูลค่ารับ (บาท)")
            headers.append("มูลค่าจ่าย (บาท)")
        for col, label in enumerate(headers):
            sheet.write(row, col, label, fmts["header"])
        row += 1

        sheet.write(row, 0, 1, fmts["text"])
        sheet.write(row, 7, data["opening_balance"], fmts["num"])
        sheet.write(row, 8, 0.0, fmts["num"])
        sheet.write(row, 9, 0.0, fmts["num"])
        sheet.write(row, 10, data["opening_balance"], fmts["num"])
        if show_value:
            sheet.write(row, 11, data["opening_value"], fmts["num"])
            sheet.write(row, 12, 0.0, fmts["num"])
            sheet.write(row, 13, 0.0, fmts["num"])
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
            sheet.write(row, 5, line["source_location"] or "", fmts["text"])
            sheet.write(row, 6, line["dest_location"] or "", fmts["text"])
            sheet.write(row, 7, line["opening"], fmts["num"])
            sheet.write(row, 8, line["in"], fmts["num"])
            sheet.write(row, 9, line["out"], fmts["num"])
            sheet.write(row, 10, line["balance"], fmts["num"])
            if show_value:
                sheet.write(row, 11, line.get("value", 0.0), fmts["num"])
                sheet.write(row, 12, line.get("value_in", 0.0), fmts["num"])
                sheet.write(row, 13, line.get("value_out", 0.0), fmts["num"])
            row += 1
