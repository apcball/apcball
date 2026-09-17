# -*- coding: utf-8 -*-
"""รายงานใบเสนอราคา Bathroom ในรูปแบบ Excel"""

import base64
import io
import os

from PIL import Image

from odoo import models
from odoo.modules.module import get_module_resource
from odoo.tools import html2plaintext


class SaleOrderBathroomXlsx(models.AbstractModel):
    _name = "report.buz_custom_quotation.report_saleorder_buz_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Quotation / BATHROOM Excel"

    def _static_image(self, *path_parts):
        """อ่านรูปจาก static ของโมดูลและคืนเป็น BytesIO สำหรับฝังใน workbook."""
        path = get_module_resource("buz_custom_quotation", "static", *path_parts)
        if not path or not os.path.isfile(path):
            return None
        with open(path, "rb") as image_file:
            return io.BytesIO(image_file.read())

    @staticmethod
    def _product_image(product):
        """คืนภาพที่มีความละเอียดสูงสุดพร้อมขนาด โดยไม่ย่อข้อมูลที่ฝังในไฟล์."""
        if not product:
            return None

        for field_name in ("image_1920", "image_1024", "image_512", "image_256", "image_128"):
            image = getattr(product, field_name, False)
            if not image:
                continue
            try:
                image_data = base64.b64decode(image)
                with Image.open(io.BytesIO(image_data)) as source_image:
                    width, height = source_image.size
                if width and height:
                    return {"data": io.BytesIO(image_data), "width": width, "height": height}
            except (OSError, ValueError, TypeError):
                # ถ้ารูปขนาดนี้เสีย ให้ลองใช้รูปย่อที่ Odoo เตรียมไว้แทน
                continue
        return None

    @staticmethod
    def _format_date(value):
        return value.strftime("%d/%m/%Y") if value else ""

    def _line_values(self, line):
        """ใช้สูตรราคาตาม QT PDF และคงยอดใน workbook เป็นตัวเลขจริง."""
        normal_price = getattr(line, "normal_price", 0.0) or 0.0
        discount_percent = getattr(line, "discount_percent", 0.0) or 0.0
        if normal_price > 0 and discount_percent > 0:
            unit_price = normal_price
            discount = round((1 - line.price_unit / normal_price) * 100, 2)
            net_price = line.price_unit
        else:
            unit_price = line.price_unit
            discount = discount_percent
            net_price = line.price_unit * (1 - discount_percent / 100.0)
        return unit_price, discount, net_price

    def generate_xlsx_report(self, workbook, data, orders):
        sheet = workbook.add_worksheet("Quotation")
        sheet.hide_gridlines(2)
        sheet.set_paper(9)  # A4
        sheet.set_portrait()
        sheet.fit_to_pages(1, 0)
        sheet.set_margins(0.25, 0.25, 0.35, 0.35)
        sheet.set_column("A:A", 7)
        sheet.set_column("B:B", 34)
        sheet.set_column("C:C", 18)
        sheet.set_column("D:D", 12)
        sheet.set_column("E:E", 16)
        sheet.set_column("F:F", 12)
        sheet.set_column("G:G", 16)
        sheet.set_column("H:H", 17)

        purple = "#933F95"
        gray = "#898989"
        common = {"font_name": "TH Sarabun New", "font_size": 12, "valign": "vcenter"}
        title_fmt = workbook.add_format({**common, "bold": True, "font_size": 20, "align": "center", "font_color": "white", "bg_color": purple})
        subtitle_fmt = workbook.add_format({**common, "bold": True, "font_size": 15, "align": "center", "font_color": purple})
        label_fmt = workbook.add_format({**common, "bold": True, "bg_color": "#F5F5F5", "text_wrap": True})
        value_fmt = workbook.add_format({**common, "bg_color": "#F5F5F5", "text_wrap": True})
        header_fmt = workbook.add_format({**common, "bold": True, "font_color": "white", "bg_color": purple, "align": "center", "text_wrap": True, "border": 1, "border_color": "white"})
        header_gray_fmt = workbook.add_format({**common, "bold": True, "font_color": "white", "bg_color": gray, "align": "center", "text_wrap": True, "border": 1, "border_color": "white"})
        text_format = {**common, "text_wrap": True, "bottom": 1, "bottom_color": "#E3E3E3"}
        text_fmt = workbook.add_format(text_format)
        center_fmt = workbook.add_format({**text_format, "align": "center"})
        money_fmt = workbook.add_format({**text_format, "align": "right", "num_format": "#,##0.00"})
        total_label_fmt = workbook.add_format({**common, "bold": True, "bottom": 1, "bottom_color": purple})
        total_fmt = workbook.add_format({**common, "bold": True, "align": "right", "num_format": "#,##0.00", "bottom": 1, "bottom_color": purple})
        grand_label_fmt = workbook.add_format({**common, "bold": True, "font_size": 14, "bottom": 3, "bottom_color": purple})
        grand_fmt = workbook.add_format({**common, "bold": True, "font_size": 14, "align": "right", "num_format": "#,##0.00", "bottom": 3, "bottom_color": purple})
        note_fmt = workbook.add_format({**common, "text_wrap": True, "valign": "top"})
        warning_fmt = workbook.add_format({**common, "bold": True, "font_color": "#CC0000", "bg_color": "#FFF3F3", "align": "center", "text_wrap": True, "border": 2, "border_color": "#CC0000"})
        percent_fmt = workbook.add_format({**common, "align": "center", "num_format": '0.##"%"', "bottom": 1, "bottom_color": "#E3E3E3"})

        row = 0
        page_breaks = []
        for order_index, order in enumerate(orders):
            if order_index:
                page_breaks.append(row)

            # ปกใช้ภาพ Cover-2 ตาม PDF และวางข้อมูลโครงการในเซลล์ด้านล่างเพื่อให้แก้ไขได้
            cover = self._static_image("img", "cover", "Cover-2.jpg")
            if cover:
                sheet.set_row(row, 280)
                sheet.insert_image(row, 0, "cover.jpg", {"image_data": cover, "x_scale": 0.30, "y_scale": 0.30, "object_position": 1})
            row += 1
            sheet.merge_range(row, 0, row, 7, "QUOTATION / BATHROOM", title_fmt)
            sheet.set_row(row, 30)
            row += 1
            sheet.merge_range(row, 0, row, 7, order.project_name or "", subtitle_fmt)
            row += 1
            meta = [
                ("To:", order.customer_name or ""),
                ("Company:", order.partner_id.name or ""),
                ("Address:", ", ".join(filter(None, [order.partner_id.street, order.partner_id.street2, order.partner_id.city, order.partner_id.zip]))),
                ("Tel:", order.partner_id.phone or ""),
                ("Email:", order.partner_id.email or ""),
                ("Date:", self._format_date(order.quotation_date or (order.date_order.date() if order.date_order else False))),
                ("Quotation No:", order.quotation_no or ""),
                ("Sale Condition:", order.payment_term_id.name or ""),
                ("Ordered By:", order.user_id.employee_ids[:1].name if order.user_id.employee_ids else order.user_id.partner_id.name or ""),
                ("Phone:", getattr(order.user_id, "mobile_phone", "") or ""),
            ]
            for label, value in meta:
                sheet.write(row, 0, label, label_fmt)
                sheet.merge_range(row, 1, row, 7, value, value_fmt)
                row += 1
            row += 1
            page_breaks.append(row)

            currency = order.currency_id.name or ""
            headers = ["No.", "Product Description", "Image", "Quantity", "Unit Price (%s)" % currency, "Discount", "Net Price (%s)" % currency, "Net Amount (%s)" % currency]
            for col, header in enumerate(headers):
                sheet.write(row, col, header, header_fmt if col < 3 else header_gray_fmt)
            sheet.set_row(row, 28)
            row += 1
            uom_formats = {}
            for sequence, line in enumerate(order.order_line, 1):
                sheet.set_row(row, 68)
                if line.display_type:
                    sheet.merge_range(row, 0, row, 7, line.name or "", subtitle_fmt if line.display_type == "line_section" else text_fmt)
                    row += 1
                    continue
                unit_price, discount, net_price = self._line_values(line)
                sheet.write(row, 0, "No. %s" % sequence, center_fmt)
                sheet.write(row, 1, line.name or "", text_fmt)
                product_image = self._product_image(line.product_id)
                if product_image:
                    # ปรับเฉพาะขนาดแสดงผล; image_data ยังคงเป็นภาพเต็มความละเอียดเพื่อคัดลอกไปใช้ต่อ
                    display_scale = min(
                        100.0 / product_image["width"],
                        72.0 / product_image["height"],
                        1.0,
                    )
                    display_width = product_image["width"] * display_scale
                    display_height = product_image["height"] * display_scale
                    sheet.insert_image(
                        row,
                        2,
                        "product.png",
                        {
                            "image_data": product_image["data"],
                            "x_scale": display_scale,
                            "y_scale": display_scale,
                            "x_offset": max(0, round((131 - display_width) / 2)),
                            "y_offset": max(0, round((91 - display_height) / 2)),
                            "object_position": 1,
                        },
                    )
                uom_name = line.product_uom.name or ""
                if uom_name not in uom_formats:
                    safe_uom = uom_name.replace('"', '""')
                    uom_formats[uom_name] = workbook.add_format({**common, "align": "center", "num_format": '#,##0.#### "%s"' % safe_uom, "bottom": 1, "bottom_color": "#E3E3E3"})
                sheet.write_number(row, 3, line.product_uom_qty or 0.0, uom_formats[uom_name])
                sheet.write_number(row, 4, unit_price or 0.0, money_fmt)
                sheet.write_number(row, 5, discount or 0.0, percent_fmt)
                sheet.write_number(row, 6, net_price or 0.0, money_fmt)
                sheet.write_number(row, 7, line.price_subtotal or 0.0, money_fmt)
                row += 1

            row += 1
            sheet.merge_range(row, 5, row, 6, "Excluding VAT (%s)" % currency, total_label_fmt)
            sheet.write_number(row, 7, order.amount_untaxed, total_fmt)
            row += 1
            sheet.merge_range(row, 5, row, 6, "VAT (%s)" % currency, total_label_fmt)
            sheet.write_number(row, 7, order.amount_tax, total_fmt)
            row += 1
            sheet.merge_range(row, 5, row, 6, "Including VAT (%s)" % currency, grand_label_fmt)
            sheet.write_number(row, 7, order.amount_total, grand_fmt)
            row += 2

            approval_state = getattr(order, "approval_state", "")
            if approval_state == "approved":
                sheet.merge_range(row, 0, row, 3, "AUTHORIZED SIGNATURE TO ORDER", center_fmt)
                sheet.merge_range(row, 4, row, 7, "AUTHORIZED SIGNATURE OF THE SELLER", center_fmt)
                row += 1
                seller_signature = self._static_image("img", "signature", "signature1.png")
                if seller_signature:
                    sheet.set_row(row, 48)
                    sheet.insert_image(row, 5, "signature.png", {"image_data": seller_signature, "x_scale": 0.45, "y_scale": 0.45, "object_position": 1})
                row += 2
                approval_date = getattr(order, "margin_approval_date", False)
                sheet.merge_range(row, 4, row, 7, "Date: %s" % (self._format_date(approval_date) or "........."), center_fmt)
                row += 1
            else:
                sheet.merge_range(row, 0, row + 1, 7, "รอการอนุมัติ Margin\nQuotation นี้ยังไม่ได้รับการอนุมัติ กรุณาขอ Approval ก่อนพิมพ์เอกสาร", warning_fmt)
                row += 3

            sheet.merge_range(row, 0, row, 7, "Terms and Conditions", subtitle_fmt)
            row += 1
            terms = html2plaintext(order.note or "")
            sheet.merge_range(row, 0, row + 3, 7, terms, note_fmt)
            sheet.set_row(row, 48)
            row += 4

        if orders:
            if page_breaks:
                sheet.set_h_pagebreaks(page_breaks)
            sheet.print_area(0, 0, row - 1, 7)
