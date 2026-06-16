from datetime import datetime

from odoo import fields, models


class ReportDPExcel(models.AbstractModel):
    _name = "report.mogen_report_dp_excel.report_dp_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "DP Excel Report"

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

    def _get_invoice_data(self, sale_order):
        invoices = sale_order.invoice_ids.filtered(lambda inv: inv.state != "cancel")
        return {
            "invoice_no": ", ".join(filter(None, invoices.mapped("name"))),
            "invoice_date": ", ".join(
                filter(None, [self._format_date(inv.invoice_date) for inv in invoices])
            ),
            "invoice_state": ", ".join(filter(None, invoices.mapped("payment_state"))),
        }

    def _get_delivery_data(self, sale_order):
        data = self.env.context.get("xlsx_export_data") or {}
        do_status = data.get("do_status")
        pickings = sale_order.picking_ids
        if do_status:
            if do_status == 'return':
                pickings = pickings.filtered(lambda p: p.picking_type_code == 'incoming')
            else:
                pickings = pickings.filtered(lambda p: p.state == do_status and p.picking_type_code == 'outgoing')
        else:
            pickings = pickings.filtered(lambda p: p.state != "cancel")
        return {
            "do_no": ", ".join(filter(None, pickings.mapped("name"))),
            "scheduled_date": ", ".join(
                filter(
                    None,
                    [self._format_date(picking.scheduled_date) for picking in pickings],
                )
            ),
            "delivery_status": ", ".join(filter(None, pickings.mapped("state"))),
        }

    def _get_pickings_by_range(self, sale_order):
        data = self.env.context.get("xlsx_export_data") or {}
        date_from = data.get("date_from")
        date_to = data.get("date_to")
        do_status = data.get("do_status")
        
        pickings = sale_order.picking_ids
        if do_status:
            if do_status == 'return':
                pickings = pickings.filtered(lambda p: p.picking_type_code == 'incoming')
            else:
                pickings = pickings.filtered(lambda p: p.state == do_status and p.picking_type_code == 'outgoing')
        else:
            pickings = pickings.filtered(lambda p: p.state != "cancel")

        if not (date_from and date_to):
            return pickings

        date_from_dt = fields.Datetime.to_datetime(f"{date_from} 00:00:00")
        date_to_dt = fields.Datetime.to_datetime(f"{date_to} 23:59:59")
        return pickings.filtered(
            lambda picking: picking.scheduled_date
            and date_from_dt <= fields.Datetime.to_datetime(picking.scheduled_date) <= date_to_dt
        )

    def _prepare_rows(self, sale_orders):
        rows = []
        sequence = 1

        for sale_order in sale_orders:
            invoice_data = self._get_invoice_data(sale_order)
            pickings = self._get_pickings_by_range(sale_order)
            if pickings:
                iter_pickings = pickings
            else:
                iter_pickings = [False]

            for picking in iter_pickings:
                moves = (
                    picking.move_ids.filtered(lambda move: move.state != "cancel")
                    if picking
                    else self.env["stock.move"]
                )
                if moves:
                    iter_moves = moves
                else:
                    iter_moves = [False]

                for move in iter_moves:
                    sale_line = move.sale_line_id if move else self.env["sale.order.line"]
                    quantity = (
                        getattr(move, "quantity", 0.0)
                        or getattr(move, "quantity_done", 0.0)
                        or move.product_uom_qty
                    ) if move else 0.0
                    if move and move.bom_line_id:
                        unit_price = move.product_id.lst_price
                        parent_bom_text = sale_line.name if sale_line else ""
                    else:
                        unit_price = sale_line.price_unit if sale_line else 0.0
                        parent_bom_text = ""
                        
                    rows.append(
                        {
                            "sequence": sequence,
                            "scheduled_date": self._format_date(picking.scheduled_date) if picking else "",
                            "so_no": self._safe_text(sale_order.name),
                            "invoice_no": invoice_data["invoice_no"],
                            "do_no": self._safe_text(picking.name) if picking else "",
                            "customer": self._safe_text(sale_order.partner_id.name),
                            "saleperson": self._safe_text(sale_order.user_id.name),
                            "sale_team": self._safe_text(sale_order.team_id.name),
                            "so_ref": self._safe_text(sale_order.client_order_ref),
                            "shipping_address": self._safe_text(
                                sale_order.partner_shipping_id.contact_address
                            ),
                            "parent_bom": self._safe_text(parent_bom_text),
                            "product_code": self._safe_text(move.product_id.default_code) if move else "",
                            "description": self._safe_text(
                                move.product_id.name
                            ) if move else "",
                            "quantity": quantity,
                            "uom": self._safe_text(move.product_uom.name) if move else "",
                            "unit_price": unit_price,
                            "sum_amount": unit_price * quantity,
                            "note": self._safe_text(picking.delivery_note) if picking else "",
                        }
                    )
                    sequence += 1

        return rows

    def _get_sale_orders(self, records):
        if records._name == "mogen.report.dp.excel.wizard" and records:
            data_ids = []
            if self.env.context.get("xlsx_export_data"):
                data_ids = self.env.context["xlsx_export_data"].get("sale_order_ids", [])
            if data_ids:
                return self.env["sale.order"].browse(data_ids).exists().sorted(
                    lambda order: (order.date_order or fields.Datetime.now(), order.name or "")
                )
        if records._name == "sale.order":
            return records.sorted(lambda order: (order.date_order or fields.Datetime.now(), order.name or ""))
        if records._name == "mogen.report.dp.excel.wizard":
            return records._get_sale_orders()
        return self.env["sale.order"]

    def _get_report_label(self, records, sale_orders, data=None):
        data = data or {}
        if records._name == "mogen.report.dp.excel.wizard" and records:
            wizard = records[0]
            date_from = data.get("date_from") or wizard.date_from
            date_to = data.get("date_to") or wizard.date_to
            return "ช่วงวันที่: %s - %s" % (
                self._format_date(date_from),
                self._format_date(date_to),
            )
        if len(sale_orders) == 1:
            return "Sale Order: %s" % self._safe_text(sale_orders.name)
        if sale_orders:
            return "จำนวนเอกสาร: %s" % len(sale_orders)
        if data.get("date_from") and data.get("date_to"):
            return "ช่วงวันที่: %s - %s" % (
                self._format_date(data["date_from"]),
                self._format_date(data["date_to"]),
            )
        return "ไม่พบข้อมูลในช่วงวันที่ที่เลือก"

    def generate_xlsx_report(self, workbook, data, records):
        self = self.with_context(xlsx_export_data=data or {})
        sale_orders = self._get_sale_orders(records)
        rows = self._prepare_rows(sale_orders)

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
        date_cell_format = workbook.add_format(
            {
                "font_name": "TH Sarabun New",
                "font_size": 12,
                "valign": "top",
                "align": "center",
                "num_format": "dd/mm/yyyy",
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
            ("DP No.", 18),
            ("SO No.", 16),
            ("Invoice No", 18),
            ("Customer", 24),
            ("Saleperson", 18),
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
        ]

        sheet = workbook.add_worksheet("DP Report")
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
        sheet.merge_range(0, 0, 0, last_col, "รายงาน DP", title_format)
        for col, (label, _) in enumerate(columns):
            sheet.write(1, col, label, header_format)

        row_idx = 2
        for row in rows:
            sheet.write(row_idx, 0, row["sequence"], center_format)
            sheet.write(row_idx, 1, row["scheduled_date"], center_format)
            sheet.write(row_idx, 2, row["do_no"], text_format)
            sheet.write(row_idx, 3, row["so_no"], text_format)
            sheet.write(row_idx, 4, row["invoice_no"], text_format)
            sheet.write(row_idx, 5, row["customer"], text_format)
            sheet.write(row_idx, 6, row["saleperson"], text_format)
            sheet.write(row_idx, 7, row["sale_team"], text_format)
            sheet.write(row_idx, 8, row["so_ref"], text_format)
            sheet.write(row_idx, 9, row["shipping_address"], text_format)
            sheet.write(row_idx, 10, row["parent_bom"], text_format)
            sheet.write(row_idx, 11, row["product_code"], text_format)
            sheet.write(row_idx, 12, row["description"], text_format)
            sheet.write_number(row_idx, 13, row["quantity"] or 0.0, number_format)
            sheet.write(row_idx, 14, row["uom"], center_format)
            sheet.write_number(row_idx, 15, row["unit_price"] or 0.0, number_format)
            sheet.write_number(row_idx, 16, row["sum_amount"] or 0.0, number_format)
            sheet.write(row_idx, 17, row["note"], text_format)
            row_idx += 1

        if not rows:
            sheet.merge_range(2, 0, 2, last_col, "ไม่พบข้อมูล", center_format)
class ReportDPExcelWizard(models.AbstractModel):
    _name = "report.mogen_report_dp_excel.report_dp_xlsx_wizard"
    _inherit = "report.mogen_report_dp_excel.report_dp_xlsx"
    _description = "DP Excel Report Wizard"
