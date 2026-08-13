from odoo import models

COLUMN_HEADERS = ["ลำดับ", "วันที่", "เอกสาร", "เลขที่", "ยอดยกมา", "รับ", "จ่าย", "คงเหลือ"]


class StockCardReportXlsx(models.AbstractModel):
    _name = "report.buz_stock_card_report.report_stock_card_xlsx"
    _inherit = "report.report_xlsx.abstract"
    _description = "Stock Card Report Excel"

    def generate_xlsx_report(self, workbook, data, wizards):
        sheet = workbook.add_worksheet("Stock Card")

        title_format = workbook.add_format({"bold": True, "font_size": 12})
        wh_format = workbook.add_format({"bold": True, "bg_color": "#F2F2F2"})
        product_format = workbook.add_format({"bold": True})
        header_format = workbook.add_format({"bold": True, "bg_color": "#D3D3D3", "border": 1})
        number_format = workbook.add_format({"num_format": "#,##0.00", "border": 1})
        date_format = workbook.add_format({"num_format": "dd/mm/yyyy", "border": 1})
        text_format = workbook.add_format({"border": 1})

        sheet.set_column("A:A", 8)
        sheet.set_column("B:B", 12)
        sheet.set_column("C:C", 22)
        sheet.set_column("D:D", 16)
        sheet.set_column("E:H", 12)

        row = 0
        for wizard in wizards:
            row = self._write_wizard(
                sheet, row, wizard, title_format, wh_format, product_format,
                header_format, number_format, date_format, text_format,
            )

    def _write_wizard(self, sheet, row, wizard, title_format, wh_format,
                       product_format, header_format, number_format,
                       date_format, text_format):
        warehouses = wizard._get_warehouses()
        for warehouse in warehouses:
            warehouse_loc_ids = wizard._get_warehouse_location_ids(warehouse)
            products = wizard._get_products_for_warehouse(warehouse_loc_ids, wizard.date_to)
            if not products:
                continue

            sheet.write(row, 0, "คลัง", wh_format)
            sheet.write(row, 1, warehouse.name, wh_format)
            row += 1

            if wizard.location_ids:
                selected_locations = wizard.location_ids.filtered(
                    lambda loc: loc.id in warehouse_loc_ids
                )
                if selected_locations:
                    sheet.write(row, 0, "ที่ตั้ง", wh_format)
                    sheet.write(
                        row, 1,
                        ", ".join(selected_locations.mapped("display_name")),
                        wh_format,
                    )
                    row += 1

            for product in products:
                opening_balance, lines = wizard.get_stock_card_lines(warehouse, product)
                if not lines and not opening_balance:
                    continue

                sheet.write(
                    row, 0,
                    "%s  %s" % (product.default_code or "", product.name),
                    product_format,
                )
                row += 1

                for col, header in enumerate(COLUMN_HEADERS):
                    sheet.write(row, col, header, header_format)
                row += 1

                for line in lines:
                    sheet.write(row, 0, line["seq"], text_format)
                    sheet.write_datetime(row, 1, line["date"], date_format)
                    sheet.write(row, 2, line["doc_type"] or "", text_format)
                    sheet.write(row, 3, line["doc_number"] or "", text_format)
                    sheet.write(row, 4, line["opening"], number_format)
                    sheet.write(row, 5, line["in_qty"], number_format)
                    sheet.write(row, 6, line["out_qty"], number_format)
                    sheet.write(row, 7, line["balance"], number_format)
                    row += 1

                row += 1

            row += 1

        return row
