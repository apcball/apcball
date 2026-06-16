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

                rows.append({
                    "sequence": sequence,
                    "date": self._format_date(invoice.invoice_date),
                    "iv_number": self._safe_text(invoice.name),
                    "sale_order": self._safe_text(sale_order.name) if sale_order else "",
                    "dp_no": ", ".join(filter(None, pickings.mapped("name"))),
                    "partner_code": self._safe_text(
                        sale_order.partner_id.partner_code
                    ) if sale_order else self._safe_text(invoice.partner_id.partner_code),
                    "customer": self._safe_text(
                        sale_order.partner_id.name
                    ) if sale_order else self._safe_text(invoice.partner_id.name),
                    "salesperson": self._safe_text(sale_order.user_id.name) if sale_order else "",
                    "sale_team": self._safe_text(sale_order.team_id.name) if sale_order else "",
                    "so_ref": self._safe_text(sale_order.client_order_ref) if sale_order else "",
                    "shipping_address": self._safe_text(
                        sale_order.partner_shipping_id.contact_address
                    ) if sale_order else "",
                    "parent_bom": self._safe_text(parent_bom_text),
                    "product_code": self._safe_text(product.default_code) if product else "",
                    "description": self._safe_text(
                        product.display_name if product else line.name
                    ),
                    "quantity": quantity,
                    "uom": self._safe_text(uom.name),
                    "unit_price": unit_price,
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

        columns = [
            ("No.", 8),
            ("Date", 14),
            ("IV number", 18),
            ("SALE ORDER", 16),
            ("DP No.", 18),
            ("Partner Code", 16),
            ("Customer", 24),
            ("Salesperson", 18),
            ("Sale Team", 18),
            ("SO.ref No.", 18),
            ("Shipping Address", 30),
            ("Parent BOM", 34),
            ("Product Code", 16),
            ("Description", 34),
            ("Quantity", 12),
            ("UoM", 10),
            ("Unit Price", 14),
            ("SUM", 14),
            ("Note", 24),
            ("Trade Channel", 16),
        ]

        sheet = workbook.add_worksheet("Invoice Report")
        sheet.set_landscape()
        sheet.set_paper(9)
        sheet.fit_to_pages(1, 0)
        sheet.repeat_rows(1, 1)
        sheet.freeze_panes(2, 0)
        sheet.set_row(0, 28)
        sheet.set_row(1, 24)

        for index, (_, width) in enumerate(columns):
            sheet.set_column(index, index, width)

        last_col = len(columns) - 1
        sheet.merge_range(0, 0, 0, last_col, "รายงาน Invoice", title_format)
        for col, (label, _) in enumerate(columns):
            sheet.write(1, col, label, header_format)

        row_idx = 2
        for row in rows:
            sheet.write(row_idx, 0, row["sequence"], center_format)
            sheet.write(row_idx, 1, row["date"], center_format)
            sheet.write(row_idx, 2, row["iv_number"], text_format)
            sheet.write(row_idx, 3, row["sale_order"], text_format)
            sheet.write(row_idx, 4, row["dp_no"], text_format)
            sheet.write(row_idx, 5, row["partner_code"], text_format)
            sheet.write(row_idx, 6, row["customer"], text_format)
            sheet.write(row_idx, 7, row["salesperson"], text_format)
            sheet.write(row_idx, 8, row["sale_team"], text_format)
            sheet.write(row_idx, 9, row["so_ref"], text_format)
            sheet.write(row_idx, 10, row["shipping_address"], text_format)
            sheet.write(row_idx, 11, row["parent_bom"], text_format)
            sheet.write(row_idx, 12, row["product_code"], text_format)
            sheet.write(row_idx, 13, row["description"], text_format)
            sheet.write_number(row_idx, 14, row["quantity"] or 0.0, number_format)
            sheet.write(row_idx, 15, row["uom"], center_format)
            sheet.write_number(row_idx, 16, row["unit_price"] or 0.0, number_format)
            sheet.write_number(row_idx, 17, row["sum_amount"] or 0.0, number_format)
            sheet.write(row_idx, 18, row["note"], text_format)
            sheet.write(row_idx, 19, row["trade_channel"], text_format)
            row_idx += 1

        if not rows:
            sheet.merge_range(2, 0, 2, last_col, "ไม่พบข้อมูล", center_format)


class ReportInvoiceExcelWizard(models.AbstractModel):
    _name = "report.buz_report_invoice_excel.report_invoice_xlsx_wizard"
    _inherit = "report.buz_report_invoice_excel.report_invoice_xlsx"
    _description = "Invoice Excel Report Wizard"
