import base64
import csv
import io

from odoo import _, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:
    openpyxl = None


class ShopeeFileImportMixin(models.AbstractModel):
    """Read an uploaded CSV/XLSX file (``file_data`` / ``file_name``)."""

    _name = "shopee.file.import.mixin"
    _description = "Shopee File Import Helpers"

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
            raise UserError(_("The uploaded file is empty.")) from exc
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
            # Read-only mode trusts the sheet's declared <dimension>; Shopee
            # exports (Go Excelize) omit it, which truncates rows to column A.
            worksheet.reset_dimensions()
            rows = worksheet.iter_rows(values_only=True)
            headers = next(rows)
        except Exception as exc:
            raise UserError(_("Invalid XLSX file: %s") % exc) from exc
        if not headers:
            raise UserError(_("The uploaded file is empty."))
        return headers, rows

    def _read_rows(self):
        try:
            content = base64.b64decode(self.file_data)
        except Exception as exc:
            raise UserError(_("The uploaded file could not be decoded.")) from exc
        if not content:
            raise UserError(_("Upload a file first."))

        filename = (self.file_name or "").lower()
        if filename.endswith(".xlsx") or content[:2] == b"PK":
            return self._read_xlsx(content)
        if filename.endswith(".xls"):
            raise UserError(_("Legacy XLS files are not supported; use CSV or XLSX."))
        return self._read_csv(content)
