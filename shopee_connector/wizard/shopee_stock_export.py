import base64
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:
    openpyxl = None


EXPORT_HEADERS = [
    "SKU",
    "Product Name",
    "Shopee Item ID",
    "Shopee Model ID",
    "Shopee Stock",
    "Last Pushed Stock",
    "Last Sync",
]


class ShopeeStockExportWizard(models.TransientModel):
    _name = "shopee.stock.export.wizard"
    _description = "Export Shopee Stock"

    file_data = fields.Binary(string="Shopee Stock File", readonly=True)
    file_name = fields.Char(string="Filename", readonly=True)
    product_count = fields.Integer(readonly=True)

    @api.model
    def _export_domain(self):
        return [("shopee_item_id", "!=", False)]

    @api.model
    def _build_xlsx(self):
        """Return (bytes, product_count) for every Shopee-linked product.

        The 'SKU' and 'Shopee Stock' columns are accepted by the stock
        import wizard, so the exported file can be edited and re-imported
        as-is.
        """
        if not openpyxl:
            raise UserError(
                _("XLSX export requires the Python module 'openpyxl'.")
            )
        products = self.env["product.product"].search_read(
            self._export_domain(),
            [
                "default_code",
                "name",
                "shopee_item_id",
                "shopee_model_id",
                "shopee_stock",
                "shopee_pushed_stock",
                "shopee_last_sync",
            ],
            order="default_code asc, id asc",
        )
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(EXPORT_HEADERS)
        for product in products:
            last_sync = product["shopee_last_sync"]
            worksheet.append([
                product["default_code"] or "",
                product["name"] or "",
                product["shopee_item_id"] or "",
                product["shopee_model_id"] or "",
                product["shopee_stock"] or 0,
                product["shopee_pushed_stock"] or 0,
                fields.Datetime.context_timestamp(self, last_sync)
                .strftime("%Y-%m-%d %H:%M:%S")
                if last_sync
                else "",
            ])
        stream = io.BytesIO()
        workbook.save(stream)
        return stream.getvalue(), len(products)

    @api.model
    def default_get(self, fields_list):
        result = super().default_get(fields_list)
        content, count = self._build_xlsx()
        result.update(
            {
                "file_data": base64.b64encode(content),
                "file_name": "shopee_stock_export.xlsx",
                "product_count": count,
            }
        )
        return result

    def action_regenerate(self):
        self.ensure_one()
        content, count = self._build_xlsx()
        self.write(
            {
                "file_data": base64.b64encode(content),
                "file_name": "shopee_stock_export.xlsx",
                "product_count": count,
            }
        )
