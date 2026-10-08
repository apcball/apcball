import re

from odoo import _, fields, models
from odoo.exceptions import UserError


HEADER_ALIASES = {
    "item_id": {"lazadaitemid", "itemid", "productid"},
    "sku_id": {"lazadaskuid", "skuid"},
    "sku": {"lazadasku", "sellersku", "sku"},
    "item_name": {"lazadaitemname", "itemname", "productname"},
    "ref": {"internalreference", "defaultcode", "odooreference", "odoosku"},
    "refill": {"refillwhenlazadastockbelow", "refillbelow"},
    "active": {"active"},
}
TRUE_VALUES = {"1", "true", "yes", "y", "t"}


class LazadaProductMappingImportWizard(models.TransientModel):
    _name = "lazada.product.mapping.import.wizard"
    _inherit = "lazada.file.import.mixin"
    _description = "Import Lazada Product Mappings"

    lazada_config_id = fields.Many2one(
        "lazada.config", string="Lazada Seller", required=True
    )
    file_data = fields.Binary(string="Mapping File", required=True)
    file_name = fields.Char(string="Filename")
    dry_run = fields.Boolean(
        string="Dry run (preview only)",
        default=True,
        help="Run the full import, report the result, then roll everything back.",
    )
    result = fields.Text(string="Result", readonly=True)

    @staticmethod
    def _normalise_header(value):
        return re.sub(r"[^a-z0-9]", "", str(value or "").strip().lower())

    @staticmethod
    def _text(value):
        """Cell -> stripped string; whole floats (Excel numbers) lose '.0'."""
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value).strip()

    @classmethod
    def _column_map(cls, headers):
        normalised = [cls._normalise_header(h) for h in headers]
        columns = {}
        for key, aliases in HEADER_ALIASES.items():
            index = next((i for i, h in enumerate(normalised) if h in aliases), None)
            if index is not None:
                columns[key] = index
        if "ref" not in columns:
            raise UserError(_("Missing required header: Internal Reference."))
        if "sku" not in columns:
            raise UserError(_("Need a Lazada SellerSku column."))
        return columns

    def _find_mapping(self, item_id, sku_id, sku):
        Mapping = self.env["lazada.product.mapping"].with_context(active_test=False)
        config = self.lazada_config_id
        mapping = Mapping.search([
            ("lazada_config_id", "=", config.id),
            ("seller_sku", "=", sku),
        ], limit=1)
        if not mapping and item_id and sku_id:
            mapping = Mapping.search([
                ("lazada_config_id", "=", config.id),
                ("lazada_item_id", "=", item_id),
                ("lazada_sku_id", "=", sku_id),
            ], limit=1)
        return mapping

    def _process_rows(self, rows, columns):
        Mapping = self.env["lazada.product.mapping"]
        stats = {"updated": 0, "created": 0, "unchanged": 0}
        problems = []
        for row_number, row in enumerate(rows, start=2):
            row = list(row)
            if not any(v is not None and str(v).strip() for v in row):
                continue

            def cell(key):
                index = columns.get(key)
                return self._text(row[index]) if index is not None and index < len(row) else ""

            ref, sku = cell("ref"), cell("sku")
            item_id, sku_id = cell("item_id"), cell("sku_id")
            label = sku or item_id or "?"
            if not ref:
                problems.append(_("Row %s (%s): empty Internal Reference.") % (row_number, label))
                continue
            if not sku:
                problems.append(_("Row %s: no SellerSku.") % row_number)
                continue
            product = Mapping.find_product_by_sku(ref)
            if not product:
                problems.append(
                    _("Row %s (%s): Internal Reference '%s' not found or ambiguous.")
                    % (row_number, label, ref)
                )
                continue

            values = {"product_id": product.id}
            if cell("refill"):
                try:
                    values["refill_below"] = int(float(cell("refill")))
                except ValueError:
                    problems.append(
                        _("Row %s (%s): invalid refill value '%s'.")
                        % (row_number, label, cell("refill"))
                    )
                    continue
            if cell("active"):
                values["active"] = cell("active").lower() in TRUE_VALUES

            mapping = self._find_mapping(item_id, sku_id, sku)
            if not mapping:
                mapping = Mapping.upsert(
                    self.lazada_config_id, sku, product=product,
                    item_id=item_id or None, sku_id=sku_id or None,
                    item_name=cell("item_name") or None,
                )
                extra = {k: v for k, v in values.items() if k != "product_id"}
                if extra:
                    mapping.write(extra)
                stats["created"] += 1
                continue
            if mapping.product_id and mapping.product_id != product:
                problems.append(
                    _("Row %s (%s): already mapped to '%s', file says '%s'. Skipped.")
                    % (row_number, label, mapping.product_id.default_code, ref)
                )
                continue
            if all(mapping[k] == v or (k == "product_id" and mapping[k].id == v)
                   for k, v in values.items()):
                stats["unchanged"] += 1
                continue
            mapping.write(values)
            stats["updated"] += 1
        return stats, problems

    def action_import(self):
        self.ensure_one()
        headers, rows = self._read_rows()
        columns = self._column_map(headers)
        with self.env.cr.savepoint(flush=False) as savepoint:
            stats, problems = self._process_rows(rows, columns)
            self.env.flush_all()
            if self.dry_run:
                savepoint.rollback()
        if self.dry_run:
            self.env.invalidate_all()
        lines = [
            _("DRY RUN - nothing saved.") if self.dry_run else _("IMPORT DONE."),
            _("Updated: %(updated)s | Created: %(created)s | Unchanged: %(unchanged)s | Skipped: %(skipped)s")
            % dict(stats, skipped=len(problems)),
        ]
        if problems:
            lines += ["", _("Skipped rows:")] + problems
        self.result = "\n".join(lines)
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }
