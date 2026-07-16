from datetime import datetime

from odoo import fields, models


class ReportInvoiceExcel(models.AbstractModel):
    _name = "report.buz_report_invoice_excel.report_invoice_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Invoice Excel Report"

    def _safe_text(self, value):
        return value or ""

    def _to_local_datetime(self, value):
        if not value:
            return None
        localized = fields.Datetime.context_timestamp(self, value)
        return localized.replace(tzinfo=None)

    def _format_date(self, value):
        if not value:
            return ""
        if isinstance(value, datetime):
            return self._to_local_datetime(value).strftime("%d/%m/%Y")
        return fields.Date.to_date(value).strftime("%d/%m/%Y")

    def _get_pickings_from_line(self, sale_line):
        moves = sale_line.move_ids.filtered(lambda m: m.state != "cancel")
        return moves.picking_id.filtered(lambda p: p.state != "cancel")

    def _prepare_rows(self, invoices):
        rows = []
        sequence = 1

        for invoice in invoices:
            for line in invoice.invoice_line_ids.filtered(
                lambda l: l.display_type not in ("line_section", "line_note")
            ):
                sale_lines = line.sale_line_ids
                sale_order = sale_lines[0].order_id if sale_lines else self.env["sale.order"]

                pos_line = getattr(line, "pos_lite_order_line_id", False)
                pos_order = pos_line.order_id if pos_line else self.env["pos.lite.order"]
                # Fallback: if no pos_line link, check if invoice itself is from a POS order
                if not pos_order and invoice.id:
                    pos_order_search = self.env["pos.lite.order"].search(
                        [("invoice_id", "=", invoice.id)], limit=1
                    )
                    pos_order = pos_order_search if pos_order_search else self.env["pos.lite.order"]

                pickings = self.env["stock.picking"]
                has_bom_line = False
                parent_bom_text = ""
                for sl in sale_lines:
                    sl_pickings = self._get_pickings_from_line(sl)
                    pickings |= sl_pickings
                    for move in sl.move_ids.filtered(lambda m: m.state != "cancel"):
                        if move.bom_line_id:
                            has_bom_line = True
                            parent_bom_text = sl.name or ""

                product = line.product_id
                if has_bom_line and product:
                    unit_price = product.lst_price
                else:
                    unit_price = line.price_unit

                quantity = line.quantity
                sum_amount = line.price_subtotal
                if invoice.move_type == "out_refund":
                    quantity = quantity * -1 if quantity > 0 else quantity
                    unit_price = unit_price * -1 if unit_price > 0 else unit_price
                    sum_amount = sum_amount * -1 if sum_amount > 0 else sum_amount

                uom = line.product_uom_id or (product.uom_id if product else self.env["uom.uom"])

                # Extract purchase price / margin from first linked sale order line or POS line
                if sale_lines:
                    sale_line = sale_lines[:1]
                    purchase_price = sale_line.purchase_price
                    margin_percent = sale_line.margin_percent
                    margin = sale_line.margin
                elif pos_line:
                    purchase_price = pos_line.standard_cost_price or 0.0
                    margin = pos_line.margin or 0.0
                    margin_percent = (pos_line.margin / pos_line.price_subtotal) if pos_line.price_subtotal else 0.0
                else:
                    purchase_price = 0.0
                    margin_percent = 0.0
                    margin = 0.0

                # Determine sales reference (sale.order or pos.lite.order)
                if sale_order:
                    ref_order = sale_order
                    ref_is_sale = True
                elif pos_order:
                    ref_order = pos_order
                    ref_is_sale = False
                else:
                    ref_order = self.env["sale.order"]
                    ref_is_sale = True

                # Add picking from POS order if applicable
                if pos_order and pos_order.picking_id:
                    pickings |= pos_order.picking_id

                # Build row with fallback logic
                so_ref = ""
                salesperson = ""
                sale_team = ""
                shipping_address = ""
                if ref_is_sale and ref_order:
                    so_ref = self._safe_text(ref_order.client_order_ref)
                    salesperson = self._safe_text(ref_order.user_id.name)
                    sale_team = self._safe_text(ref_order.team_id.name)
                    shipping_address = self._safe_text(ref_order.partner_shipping_id.contact_address)
                elif not ref_is_sale and ref_order:
                    so_ref = self._safe_text(ref_order.name)
                    salesperson = self._safe_text(ref_order.employee_id.name)
                    sale_team = self._safe_text(ref_order.location_id.display_name or "")
                    shipping_address = self._safe_text(
                        ref_order.partner_shipping_id.contact_address if ref_order.partner_shipping_id else ""
                    )

                rows.append({
                    "sequence": sequence,
                    "date": self._format_date(invoice.invoice_date),
                    "iv_number": self._safe_text(invoice.name),
                    "sale_order": self._safe_text(sale_order.name) if sale_order else "",
                    "pos_order": self._safe_text(pos_order.name) if pos_order else "",
                    "dp_no": ", ".join(filter(None, pickings.mapped("name"))),
                    "dispatch_doc": ", ".join(filter(None, pickings.mapped("buz_dispatch_document_name"))),
                    "partner_code": self._safe_text(
                        ref_order.partner_id.partner_code if ref_order else invoice.partner_id.partner_code
                    ),
                    "customer": self._safe_text(
                        ref_order.partner_id.name if ref_order else invoice.partner_id.name
                    ),
                    "salesperson": salesperson,
                    "sale_team": sale_team,
                    "so_ref": so_ref,
                    "shipping_address": shipping_address,
                    "parent_bom": self._safe_text(parent_bom_text),
                    "product_code": self._safe_text(product.default_code) if product else "",
                    "description": self._safe_text(
                        product.display_name if product else line.name
                    ),
                    "quantity": quantity,
                    "uom": self._safe_text(uom.name),
                    "unit_price": unit_price,
                    "purchase_price": purchase_price,
                    "margin_percent": margin_percent,
                    "margin": margin,
                    "sum_amount": sum_amount,
                    "note": ", ".join(filter(None, pickings.mapped("delivery_note"))),
                    "trade_channel": self._safe_text(
                        getattr(invoice, "trade_channel", "") or ""
                    ),
                })
                sequence += 1

        return rows

    def _get_invoices(self, records):
        if records._name == "buz.invoice.report.excel.wizard" and records:
            data_ids = []
            if self.env.context.get("xlsx_export_data"):
                data_ids = self.env.context["xlsx_export_data"].get("invoice_ids", [])
            if data_ids:
                return self.env["account.move"].browse(data_ids).exists().sorted(
                    lambda inv: (inv.invoice_date or fields.Date.today(), inv.name or "")
                )
        if records._name == "account.move":
            return records.filtered(
                lambda m: m.move_type in ("out_invoice", "out_refund")
            ).sorted(
                lambda inv: (inv.invoice_date or fields.Date.today(), inv.name or "")
            )
        if records._name == "buz.invoice.report.excel.wizard":
            return records._get_invoices()
        return self.env["account.move"]

    def _get_report_label(self, records, invoices, data=None):
        data = data or {}
        if records._name == "buz.invoice.report.excel.wizard" and records:
            wizard = records[0]
            date_from = data.get("date_from") or wizard.date_from
            date_to = data.get("date_to") or wizard.date_to
            return "ช่วงวันที่: %s - %s" % (
                self._format_date(date_from),
                self._format_date(date_to),
            )
        if len(invoices) == 1:
            return "Invoice: %s" % self._safe_text(invoices.name)
        if invoices:
            return "จำนวนเอกสาร: %s" % len(invoices)
        if data.get("date_from") and data.get("date_to"):
            return "ช่วงวันที่: %s - %s" % (
                self._format_date(data["date_from"]),
                self._format_date(data["date_to"]),
            )
        return "ไม่พบข้อมูลในช่วงวันที่ที่เลือก"

    def generate_xlsx_report(self, workbook, data, records):
        self = self.with_context(xlsx_export_data=data or {})
        invoices = self._get_invoices(records)
        rows = self._prepare_rows(invoices)

        title_format = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "font_name": "TH Sarabun New",
                "font_size": 16,
                "border": 1,
            }
        )
        header_format = workbook.add_format(
            {
                "bold": True,
                "align": "center",
                "valign": "vcenter",
                "text_wrap": True,
                "font_name": "TH Sarabun New",
                "font_size": 12,
                "border": 1,
                "bg_color": "#D9D9D9",
            }
        )
        text_format = workbook.add_format(
            {
                "font_name": "TH Sarabun New",
                "font_size": 12,
                "valign": "top",
                "text_wrap": True,
                "border": 1,
            }
        )
        center_format = workbook.add_format(
            {
                "font_name": "TH Sarabun New",
                "font_size": 12,
                "valign": "top",
                "align": "center",
                "border": 1,
            }
        )
        number_format = workbook.add_format(
            {
                "font_name": "TH Sarabun New",
                "font_size": 12,
                "valign": "top",
                "align": "right",
                "num_format": "#,##0.00",
                "border": 1,
            }
        )
        percent_format = workbook.add_format(
            {
                "font_name": "TH Sarabun New",
                "font_size": 12,
                "valign": "top",
                "align": "right",
                "num_format": "0.00%",
                "border": 1,
            }
        )

        show_cost = self.env.user.has_group(
            "buz_report_invoice_excel.group_invoice_report_manager"
        )

        columns = [
            ("No.", 8, "sequence", center_format, False),
            ("Date", 14, "date", center_format, False),
            ("IV number", 18, "iv_number", text_format, False),
            ("SALE ORDER", 16, "sale_order", text_format, False),
            ("POS Order", 16, "pos_order", text_format, False),
            ("Picking Doc", 18, "dp_no", text_format, False),
            ("Dispatch Doc", 18, "dispatch_doc", text_format, False),
            ("Partner Code", 16, "partner_code", text_format, False),
            ("Customer", 24, "customer", text_format, False),
            ("Salesperson", 18, "salesperson", text_format, False),
            ("Sale Team", 18, "sale_team", text_format, False),
            ("SO.ref No.", 18, "so_ref", text_format, False),
            ("Shipping Address", 30, "shipping_address", text_format, False),
            ("Parent BOM", 34, "parent_bom", text_format, False),
            ("Product Code", 16, "product_code", text_format, False),
            ("Description", 34, "description", text_format, False),
            ("Quantity", 12, "quantity", number_format, True),
            ("UoM", 10, "uom", center_format, False),
            ("Unit Price", 14, "unit_price", number_format, True),
        ]
        if show_cost:
            columns.append(("Cost", 14, "purchase_price", number_format, True))
        columns += [
            ("Margin %", 12, "margin_percent", percent_format, True),
            ("Margin", 14, "margin", number_format, True),
            ("SUM", 14, "sum_amount", number_format, True),
            ("Note", 24, "note", text_format, False),
            ("Trade Channel", 16, "trade_channel", text_format, False),
        ]

        sheet = workbook.add_worksheet("Invoice Report")
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(1, 1)
        sheet.freeze_panes(2, 0)
        sheet.set_row(0, 28)
        sheet.set_row(1, 24)

        for index, col in enumerate(columns):
            sheet.set_column(index, index, col[1])

        last_col = len(columns) - 1
        sheet.merge_range(0, 0, 0, last_col, "รายงาน Invoice", title_format)
        for col, entry in enumerate(columns):
            sheet.write(1, col, entry[0], header_format)

        row_idx = 2
        for row in rows:
            for col, (_label, _width, key, fmt, is_num) in enumerate(columns):
                value = row.get(key, "")
                if is_num:
                    sheet.write_number(row_idx, col, value or 0.0, fmt)
                else:
                    sheet.write(row_idx, col, value, fmt)
            row_idx += 1

        if not rows:
            sheet.merge_range(2, 0, 2, last_col, "ไม่พบข้อมูล", center_format)


class ReportInvoiceExcelWizard(models.AbstractModel):
    _name = "report.buz_report_invoice_excel.report_invoice_xlsx_wizard"
    _inherit = "report.buz_report_invoice_excel.report_invoice_xlsx"
    _description = "Invoice Excel Report Wizard"
