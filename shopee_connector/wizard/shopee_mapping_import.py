import re

from odoo import _, fields, models
from odoo.exceptions import UserError


HEADER_ALIASES = {
    "item_id": {"shopeeitemid", "itemid"},
    "model_id": {"shopeemodelid", "modelid"},
    "sku": {"shopeesku", "sku", "modelsku", "itemsku"},
    "item_name": {"shopeeitemname", "itemname"},
    "ref": {"internalreference", "defaultcode", "odooreference", "odoosku"},
    "refill": {"refillwhenshopeestockbelow", "refillbelow"},
    "active": {"active"},
}
TRUE_VALUES = {"1", "true", "yes", "y", "t"}


class ShopeeProductMappingImportWizard(models.TransientModel):
    _name = "shopee.product.mapping.import.wizard"
    _inherit = "shopee.file.import.mixin"
    _description = "Import Shopee Product Mappings"

    shopee_config_id = fields.Many2one(
        "shopee.config", string="Shopee Shop", required=True
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
        if "item_id" not in columns and "sku" not in columns:
            raise UserError(_("Need a Shopee Item ID and/or Shopee SKU column."))
        return columns

    def _find_mapping(self, item_id, model_id, sku):
        Mapping = self.env["shopee.product.mapping"].with_context(active_test=False)
        config = self.shopee_config_id
        mapping = Mapping
        if item_id:
            mapping = Mapping.search([
                ("shopee_config_id", "=", config.id),
                ("shopee_item_id", "=", item_id),
                ("shopee_model_id", "=", model_id or False),
            ], limit=1)
        if not mapping and sku:
            mapping = Mapping.search([
                ("shopee_config_id", "=", config.id),
                ("shopee_sku", "=", sku),
            ], limit=1)
        return mapping

    def _process_rows(self, rows, columns):
        Mapping = self.env["shopee.product.mapping"]
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
            item_id, model_id = cell("item_id"), cell("model_id")
            label = sku or item_id or "?"
            if not ref:
                problems.append(_("Row %s (%s): empty Internal Reference.") % (row_number, label))
                continue
            if not sku and not item_id:
                problems.append(_("Row %s: no SKU and no Item ID.") % row_number)
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

            mapping = self._find_mapping(item_id, model_id, sku)
            if not mapping:
                Mapping.upsert(
                    self.shopee_config_id, sku=sku or None, product=product,
                    item_id=item_id or None, model_id=model_id or None,
                    item_name=cell("item_name") or None,
                )
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
