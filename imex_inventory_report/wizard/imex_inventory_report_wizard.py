# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval


class ImexInventoryReportWizard(models.TransientModel):
    _name = "imex.inventory.report.wizard"
    _description = "Imex Inventory Report Wizard"

    date_from = fields.Date(string="Start Date")
    date_to = fields.Date(string="End Date")
    location_id = fields.Many2one(
        comodel_name="stock.location", string="Location")
    product_ids = fields.Many2many(
        comodel_name="product.product", string="Products")
    len_product = fields.Integer()
    product_category_ids = fields.Many2many(
        comodel_name="product.category", string="Product Categories")
    is_groupby_location = fields.Boolean(string="Group by Locations", default=True,
                                         help="If checked, it will calculate the detailed quantity of input and output, including internal transfers,. If not, it will only calculate the quantity of input and output for transfers between internal locations and external locations.")
            
    @api.onchange('product_ids')
    def _onchange_product_ids(self):
        for record in self:
            record.len_product = len(record.product_ids)

    def _prepare_imex_inventory_report(self):
        return {
            "date_from": self.date_from or "1900-01-01",
            "date_to": self.date_to or fields.Date.context_today(self),
            "product_ids": [(6, 0, self.product_ids.ids)] or None,
            "location_id": self.location_id.id or None,
            "product_category_ids": [(6, 0, self.product_category_ids.ids)] or None,
            "is_groupby_location": self.is_groupby_location,
        }

    def button_view(self):
        vals = {}
        filters = self._prepare_imex_inventory_report()
        report = self.create(filters)
        # init view data
        self.env["imex.inventory.report"].init_results(report)
        action = self.env.ref("imex_inventory_report.action_imex_inventory_report_tree_view")
        vals = action.sudo().read()[0]
        context = vals.get("context", {})
        if context:
            context = safe_eval(context)
        context["filters"] = filters
        vals["context"] = context
        return vals

    def button_view_details(self):
        filters = self._prepare_imex_inventory_report()
        return self.env["imex.inventory.details.report"].view_report_details(filters)