import base64
import datetime
import io

from odoo import _, fields, models
from odoo.exceptions import UserError

try:
    import openpyxl
except ImportError:
    openpyxl = None

REQUIRED_COLUMNS = ["product_code", "product_name", "warehouse", "quantity"]
ALL_COLUMNS = [
    "doc_no",
    "product_code",
    "product_name",
    "product_status",
    "warehouse",
    "layout",
    "lac",
    "quantity",
    "date",
]


def _parse_date(value):
    """Coerce an Excel cell into a date, or None when empty/unparseable."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value.date()
    if isinstance(value, datetime.date):
        return value
    try:
        return fields.Date.to_date(str(value).strip())
    except (ValueError, TypeError):
        return None


class StockCountTagImportWizard(models.TransientModel):
    _name = "buz.stock.count.tag.import.wizard"
    _description = "Import Stock Count Tag Lines"

    tag_id = fields.Many2one("buz.stock.count.tag", required=True)
    file_data = fields.Binary(string="Excel File", required=True)
    file_name = fields.Char()
    has_header = fields.Boolean(default=True, string="First row is header")
    state = fields.Selection(
        [("upload", "Upload"), ("preview", "Preview")], default="upload"
    )
    preview_ids = fields.One2many(
        "buz.stock.count.tag.import.preview", "wizard_id", string="Preview Lines"
    )
    valid_count = fields.Integer(readonly=True)
    warning_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_preview(self):
        self.ensure_one()
        if not openpyxl:
            raise UserError(_("Python module 'openpyxl' is required."))

        self.preview_ids.unlink()

        try:
            content = base64.b64decode(self.file_data)
            wb = openpyxl.load_workbook(
                filename=io.BytesIO(content), read_only=True, data_only=True
            )
            ws = wb.active
        except Exception as e:
            raise UserError(_("Invalid file format: %s") % str(e))

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            raise UserError(_("File is empty."))

        if self.has_header:
            header_row = [str(h).strip() if h else "" for h in rows[0]]
            missing = [c for c in REQUIRED_COLUMNS if c not in header_row]
            if missing:
                raise UserError(_("Missing required columns: %s") % ", ".join(missing))
            col_index = {name: header_row.index(name) for name in ALL_COLUMNS if name in header_row}
            data_rows = rows[1:]
        else:
            col_index = {name: i for i, name in enumerate(ALL_COLUMNS)}
            data_rows = rows

        def get(row, key):
            idx = col_index.get(key)
            if idx is None or idx >= len(row):
                return None
            return row[idx]

        seen_codes = {}
        for row in data_rows:
            code = get(row, "product_code")
            if code:
                seen_codes[code] = seen_codes.get(code, 0) + 1

        preview_vals = []
        for row_number, row in enumerate(data_rows, start=2 if self.has_header else 1):
            if row is None or all(v is None for v in row):
                continue

            product_code = get(row, "product_code")
            product_name = get(row, "product_name")
            warehouse = get(row, "warehouse")
            quantity_raw = get(row, "quantity")

            status = "ok"
            message = ""

            if not product_code or not product_name or not warehouse or quantity_raw is None:
                status = "error"
                message = _("Missing required field(s): product_code / product_name / warehouse / quantity")
            else:
                try:
                    quantity = float(quantity_raw)
                    if quantity < 0:
                        status = "error"
                        message = _("Quantity must be >= 0")
                except (TypeError, ValueError):
                    status = "error"
                    message = _("Quantity must be numeric")

            if status == "ok" and product_code and seen_codes.get(product_code, 0) > 1:
                status = "warning"
                message = _("Duplicate product_code in this import")

            preview_vals.append(
                {
                    "wizard_id": self.id,
                    "row_number": row_number,
                    "doc_no": str(get(row, "doc_no")).strip() if get(row, "doc_no") else "",
                    "product_code": product_code or "",
                    "product_name": product_name or "",
                    "product_status": get(row, "product_status") or "",
                    "warehouse": warehouse or "",
                    "layout": get(row, "layout") or "",
                    "lac": get(row, "lac") or "",
                    "quantity": quantity_raw if isinstance(quantity_raw, (int, float)) else 0.0,
                    "date": _parse_date(get(row, "date")),
                    "status": status,
                    "message": message,
                }
            )

        self.env["buz.stock.count.tag.import.preview"].create(preview_vals)

        self.write(
            {
                "state": "preview",
                "valid_count": sum(1 for p in preview_vals if p["status"] == "ok"),
                "warning_count": sum(1 for p in preview_vals if p["status"] == "warning"),
                "error_count": sum(1 for p in preview_vals if p["status"] == "error"),
            }
        )
        return self._reopen()

    def action_import(self):
        self.ensure_one()
        if self.tag_id.state != "draft":
            raise UserError(_("Lines can only be imported into a Tag in Draft state."))

        importable = self.preview_ids.filtered(lambda p: p.status != "error")
        if not importable:
            raise UserError(_("There are no valid lines to import."))

        line_vals = [
            {
                "tag_id": self.tag_id.id,
                "sequence": p.row_number,
                "doc_no": p.doc_no,
                "product_code": p.product_code,
                "product_name": p.product_name,
                "product_status": p.product_status,
                "warehouse": p.warehouse,
                "layout": p.layout,
                "lac": p.lac,
                "quantity": p.quantity,
                "date": p.date,
                "import_status": p.status,
                "import_message": p.message,
            }
            for p in importable
        ]
        self.env["buz.stock.count.tag.line"].create(line_vals)
        self.tag_id.write({"state": "imported"})
        return {"type": "ir.actions.act_window_close"}


class StockCountTagImportPreview(models.TransientModel):
    _name = "buz.stock.count.tag.import.preview"
    _description = "Stock Count Tag Import Preview Line"
    _order = "row_number"

    wizard_id = fields.Many2one(
        "buz.stock.count.tag.import.wizard", required=True, ondelete="cascade"
    )
    row_number = fields.Integer()
    doc_no = fields.Char(string="Doc No.")
    product_code = fields.Char()
    product_name = fields.Char()
    product_status = fields.Char()
    warehouse = fields.Char()
    layout = fields.Char()
    lac = fields.Char()
    quantity = fields.Float()
    date = fields.Date()
    status = fields.Selection(
        [("ok", "OK"), ("warning", "Warning"), ("error", "Error")]
    )
    message = fields.Char()
