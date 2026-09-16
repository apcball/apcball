import base64
import csv
import io
import re
from decimal import Decimal, InvalidOperation

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:
    openpyxl = None


SKU_HEADERS = {
    "sku",
    "defaultcode",
    "itemsku",
    "modelsku",
    "productcode",
    "productsku",
    "sellersku",
    "variationsku",
}
QUANTITY_HEADERS = {
    "availablequantity",
    "availablestock",
    "currentstock",
    "inventory",
    "lazadastock",
    "qty",
    "quantity",
    "sellerstock",
    "stock",
    "totalavailablestock",
    "totalstock",
}


class LazadaStockImportWizard(models.TransientModel):
    _name = "lazada.stock.import.wizard"
    _description = "Import Lazada Stock"

    file_data = fields.Binary(string="Lazada Stock File", required=True)
    file_name = fields.Char(string="Filename")

    @staticmethod
    def _normalise_header(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())

    @staticmethod
    def _sku_value(value):
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip()

    @classmethod
    def _column_indexes(cls, headers):
        normalised = [cls._normalise_header(header) for header in headers]
        sku_index = next(
            (index for index, header in enumerate(normalised) if header in SKU_HEADERS),
            None,
        )
        quantity_index = next(
            (
                index
                for index, header in enumerate(normalised)
                if header in QUANTITY_HEADERS
            ),
            None,
        )
        missing = []
        if sku_index is None:
            missing.append(_("SKU"))
        if quantity_index is None:
            missing.append(_("quantity/stock"))
        if missing:
            raise UserError(
                _("Missing required Lazada file header(s): %s") % ", ".join(missing)
            )
        return sku_index, quantity_index

    def _read_csv(self, content):
        text = None
        for encoding in ("utf-8-sig", "utf-8", "cp874", "latin-1"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise UserError(_("The CSV file encoding is not supported."))

        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel
        reader = csv.reader(io.StringIO(text), dialect)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise UserError(_("The Lazada stock file is empty.")) from exc
        return headers, reader

    def _read_xlsx(self, content):
        if not openpyxl:
            raise UserError(
                _("XLSX import requires the Python module 'openpyxl'.")
            )
        try:
            workbook = openpyxl.load_workbook(
                filename=io.BytesIO(content), read_only=True, data_only=True
            )
            worksheet = workbook.active
            rows = worksheet.iter_rows(values_only=True)
            headers = next(rows)
        except Exception as exc:
            raise UserError(_("Invalid XLSX file: %s") % exc) from exc
        if not headers:
            raise UserError(_("The Lazada stock file is empty."))
        return headers, rows

    def _read_rows(self):
        try:
            content = base64.b64decode(self.file_data)
        except Exception as exc:
            raise UserError(_("The uploaded file could not be decoded.")) from exc
        if not content:
            raise UserError(_("Upload a Lazada stock file first."))

        filename = (self.file_name or "").lower()
        if filename.endswith(".xlsx") or content[:2] == b"PK":
            return self._read_xlsx(content)
        if filename.endswith(".xls"):
            raise UserError(_("Legacy XLS files are not supported; use CSV or XLSX."))
        return self._read_csv(content)

    @staticmethod
    def _quantity_value(value, sku, row_number):
        if value is None or (isinstance(value, str) and not value.strip()):
            raise UserError(
                _("Invalid quantity for SKU '%s' on row %s: value is empty.")
                % (sku, row_number)
            )
        try:
            quantity = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise UserError(
                _("Invalid quantity for SKU '%s' on row %s: %s")
                % (sku, row_number, value)
            )
        if not quantity.is_finite() or quantity < 0 or quantity != quantity.to_integral_value():
            raise UserError(
                _("Invalid quantity for SKU '%s' on row %s: %s")
                % (sku, row_number, value)
            )
        return int(quantity)

    def action_import(self):
        self.ensure_one()
        headers, rows = self._read_rows()
        sku_index, quantity_index = self._column_indexes(headers)

        values = []
        seen_skus = set()
        unknown_skus = set()
        Product = self.env["product.product"]
        for row_number, row in enumerate(rows, start=2):
            row = list(row)
            if not any(value is not None and str(value).strip() for value in row):
                continue
            sku = self._sku_value(row[sku_index] if sku_index < len(row) else None)
            if not sku:
                raise UserError(_("Missing SKU on row %s.") % row_number)
            if sku in seen_skus:
                raise UserError(_("Duplicate SKU '%s' on row %s.") % (sku, row_number))
            seen_skus.add(sku)
            quantity = self._quantity_value(
                row[quantity_index] if quantity_index < len(row) else None,
                sku,
                row_number,
            )
            product = Product.search([("default_code", "=", sku)], limit=1)
            if not product:
                unknown_skus.add(sku)
            values.append((product, quantity))

        if unknown_skus:
            raise UserError(
                _("Unknown SKU(s); no products were created: %s")
                % ", ".join(sorted(unknown_skus))
            )
        if not values:
            raise UserError(_("No stock rows were found in the file."))

        for product, quantity in values:
            product.write({"lazada_stock": quantity})
        return {"type": "ir.actions.act_window_close"}
    