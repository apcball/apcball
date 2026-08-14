from urllib.parse import urlencode

from odoo import fields, models


class WipManufacturingExportWizard(models.TransientModel):
    _name = "buz.wip.manufacturing.export.wizard"
    _description = "WIP Manufacturing Report Export Wizard"

    date_from = fields.Date(
        string="Date From", required=True,
        default=lambda self: fields.Date.context_today(self).replace(day=1),
    )
    date_to = fields.Date(
        string="Date To", required=True,
        default=lambda self: fields.Date.context_today(self),
    )
    mo_ids = fields.Many2many("mrp.production", string="Manufacturing Orders")
    product_ids = fields.Many2many(
        "product.product", "buz_wip_export_wizard_product_rel", string="Finished Product",
    )
    component_ids = fields.Many2many(
        "product.product", "buz_wip_export_wizard_component_rel", string="Component",
    )
    location_ids = fields.Many2many(
        "stock.location", string="Store / Location", domain=[("usage", "=", "internal")],
    )
    status_list = fields.Selection(
        [
            ("progress_done", "In Progress + Done"),
            ("done", "Done Only"),
            ("all", "All (except cancelled)"),
        ],
        string="Status", default="progress_done", required=True,
    )
    cost_source = fields.Selection(
        [
            ("svl", "Stock Valuation"),
            ("move_unit_cost", "Move Unit Cost"),
            ("standard_price", "Standard Cost"),
        ],
        string="Cost Source", default="svl", required=True,
    )
    show_valuation_detail = fields.Boolean(string="Show Valuation Detail")

    def _status_list_values(self):
        return {
            "progress_done": ["progress", "to_close", "done"],
            "done": ["done"],
            "all": ["draft", "confirmed", "progress", "to_close", "done"],
        }[self.status_list]

    def action_export_xlsx(self):
        self.ensure_one()
        params = {
            "date_from": self.date_from,
            "date_to": self.date_to,
            "status_list": ",".join(self._status_list_values()),
            "cost_source": self.cost_source,
            "show_valuation_detail": "1" if self.show_valuation_detail else "0",
            "company_id": self.env.company.id,
            "mo_ids": ",".join(str(i) for i in self.mo_ids.ids),
            "product_ids": ",".join(str(i) for i in self.product_ids.ids),
            "component_ids": ",".join(str(i) for i in self.component_ids.ids),
            "location_ids": ",".join(str(i) for i in self.location_ids.ids),
        }
        return {
            "type": "ir.actions.act_url",
            "url": "/wip_manufacturing_report/export_xlsx?" + urlencode(params),
            "target": "new",
        }
