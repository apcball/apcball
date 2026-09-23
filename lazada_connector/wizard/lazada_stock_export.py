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
    "Lazada Item ID",
    "Lazada SKU ID",
    "Lazada Stock",
    "Last Pushed Stock",
    "Last Sync",
]


class LazadaStockExportWizard(models.TransientModel):
    _name = "lazada.stock.export.wizard"
    _description = "Export Lazada Stock"

    file_data = fields.Binary(string="Lazada Stock File", readonly=True)
    file_name = fields.Char(string="Filename", readonly=True)
    product_count = fields.Integer(readonly=True)

    @api.model
    def _export_domain(self):
        return [("lazada_item_id", "!=", False)]

    @api.model
    def _build_xlsx(self):
        """Return (bytes, product_count) for every Lazada-linked product.

        The 'SKU' and 'Lazada Stock' columns are accepted by the stock
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
                "lazada_item_id",
                "lazada_sku_id",
                "lazada_stock",
                "lazada_pushed_stock",
                "lazada_last_sync",
            ],
            order="default_code asc, id asc",
        )
        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.append(EXPORT_HEADERS)
        for product in products:
            last_sync = product["lazada_last_sync"]
            worksheet.append([
                product["default_code"] or "",
                product["name"] or "",
                product["lazada_item_id"] or "",
                product["lazada_sku_id"] or "",
                product["lazada_stock"] or 0,
                product["lazada_pushed_stock"] or 0,
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
                "file_name": "lazada_stock_export.xlsx",
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
                "file_name": "lazada_stock_export.xlsx",
                "product_count": count,
            }
        )
