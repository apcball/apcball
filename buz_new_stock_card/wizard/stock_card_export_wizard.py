from urllib.parse import urlencode

from odoo import api, fields, models


class StockCardExportWizard(models.TransientModel):
    _name = "buz.stock.card.export.wizard"
    _description = "Stock Card Export Wizard"

    product_id = fields.Many2one("product.product", string="Product")
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    report_scope = fields.Boolean(string="Combine selected scope", default=False)
    include_children = fields.Boolean(string="Include child locations", default=True)
    date_from = fields.Date(string="Date From", required=True,
                             default=lambda self: fields.Date.context_today(self).replace(day=1))
    date_to = fields.Date(string="Date To", required=True,
                           default=lambda self: fields.Date.context_today(self))
    warehouse_ids = fields.Many2many("stock.warehouse", string="Warehouses")
    location_ids = fields.Many2many(
        "stock.location", string="Locations",
        domain=[("usage", "in", ["view", "internal"])],
    )
    show_movements_only = fields.Boolean(string="Show Movements Only")
    include_cost_lot = fields.Boolean(string="ต้นทุน + Lot", default=True)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        self.warehouse_ids = self.warehouse_ids.filtered(lambda w: w.company_id == self.company_id)
        self.location_ids = self.location_ids.filtered(lambda loc: not loc.company_id or loc.company_id == self.company_id)
        if self.product_id.company_id and self.product_id.company_id != self.company_id:
            self.product_id = False

    def action_export_xlsx(self):
        self.ensure_one()
        all_mode = not self.product_id and not self.warehouse_ids and not self.location_ids
        # product only (no warehouse/location) is supported: the controller
        # reports the product across every location where it has stock/movement.
        can_see_value = self.env.user.has_group("buz_new_stock_card.group_stock_card_see_value")
        params = {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "show_movements_only": "1" if self.show_movements_only else "0",
            "include_cost_lot": "1" if self.include_cost_lot and can_see_value else "0",
            "company_id": self.company_id.id,
            "report_scope": "1" if self.report_scope else "0",
            "include_children": "1" if self.include_children else "0",
        }
        if not all_mode:
            if self.product_id:
                params["product_id"] = self.product_id.id
            params["warehouse_ids"] = ",".join(str(i) for i in self.warehouse_ids.ids)
            params["location_ids"] = ",".join(str(i) for i in self.location_ids.ids)
        return {
            "type": "ir.actions.act_url",
            "url": "/stock_card/export_xlsx?" + urlencode(params),
            "target": "new",
        }
