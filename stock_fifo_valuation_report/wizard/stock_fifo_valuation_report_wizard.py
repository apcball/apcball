# -*- coding: utf-8 -*-
from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval


class StockFifoValuationReportWizard(models.TransientModel):
    _name = "stock.fifo.valuation.report.wizard"
    _description = "Stock FIFO Valuation Report Wizard"

    date_from = fields.Date(string="Start Date")
    date_to = fields.Date(string="End Date")
    warehouse_ids = fields.Many2many(
        comodel_name="stock.warehouse", string="Warehouses",
        help="Leave empty to include all warehouses.")
    product_ids = fields.Many2many(
        comodel_name="product.product", string="Products")
    len_product = fields.Integer()
    product_category_ids = fields.Many2many(
        comodel_name="product.category", string="Product Categories")

    @api.onchange('product_ids')
    def _onchange_product_ids(self):
        for record in self:
            record.len_product = len(record.product_ids)

    def _prepare_stock_fifo_valuation_report(self):
        return {
            "date_from": self.date_from or "1900-01-01",
            "date_to": self.date_to or fields.Date.context_today(self),
            "product_ids": [(6, 0, self.product_ids.ids)] or None,
            "warehouse_ids": [(6, 0, self.warehouse_ids.ids)] or None,
            "product_category_ids": [(6, 0, self.product_category_ids.ids)] or None,
        }

    def button_view(self):
        filters = self._prepare_stock_fifo_valuation_report()
        report = self.create(filters)
        self.env["stock.fifo.valuation.report"].init_results(report)
        action = self.env.ref(
            "stock_fifo_valuation_report.action_stock_fifo_valuation_report_tree_view")
        vals = action.sudo().read()[0]
        context = vals.get("context", {})
        if context:
            context = safe_eval(context)
        context["filters"] = filters
        vals["context"] = context
        return vals

    def button_view_details(self):
        filters = self._prepare_stock_fifo_valuation_report()
        return self.env["stock.fifo.valuation.details.report"].view_report_details(filters)
