import re
from decimal import Decimal, InvalidOperation

from odoo import _, fields, models
from odoo.exceptions import UserError


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
    "qty",
    "quantity",
    "sellerstock",
    "shopeestock",
    "stock",
    "totalavailablestock",
    "totalstock",
}


class ShopeeStockImportWizard(models.TransientModel):
    _name = "shopee.stock.import.wizard"
    _inherit = "shopee.file.import.mixin"
    _description = "Import Shopee Stock"

    file_data = fields.Binary(string="Shopee Stock File", required=True)
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
                _("Missing required Shopee file header(s): %s") % ", ".join(missing)
            )
        return sku_index, quantity_index

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
            product = Product.search([("default_code", "=", sku)], limit=2)
            if len(product) > 1:
                raise UserError(_("SKU '%s' matches multiple products; no stock was imported.") % sku)
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
            product.write({"shopee_stock": quantity})
        return {"type": "ir.actions.act_window_close"}
