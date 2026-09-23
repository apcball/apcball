from odoo import api, fields, models
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = "product.product"

    shopee_linked = fields.Boolean(
        string="Shopee Linked",
        compute="_compute_shopee_linked",
        search="_search_shopee_linked",
        help="True if this variant is linked to a Shopee item/model.",
    )
    shopee_item_id = fields.Char(
        string="Shopee Item ID", readonly=True, copy=False
    )
    shopee_model_id = fields.Char(
        string="Shopee Model ID",
        readonly=True,
        copy=False,
        help="Shopee model (variant) id. Empty for single-SKU items.",
    )
    shopee_stock = fields.Integer(
        string="Shopee Available Stock",
        readonly=True,
        copy=False,
        help="Stock quantity as last reported by Shopee. Reference only - "
        "not synced back into Odoo's own inventory.",
    )
    shopee_last_sync = fields.Datetime(
        string="Shopee Last Stock Sync", readonly=True, copy=False
    )
    shopee_sync_stock_out = fields.Boolean(
        string="Push Stock to Shopee",
        default=True,
        copy=False,
        help="When enabled and the shop connection has stock push turned on, "
        "this variant's Odoo free-to-use quantity is pushed to Shopee.",
    )
    shopee_pushed_stock = fields.Integer(
        string="Shopee Last Pushed Stock", readonly=True, copy=False,
        help="Last quantity sent to Shopee. Used to skip unchanged pushes.",
    )
    shopee_stock_push_date = fields.Datetime(
        string="Shopee Last Stock Push", readonly=True, copy=False
    )

    @api.depends("shopee_item_id")
    def _compute_shopee_linked(self):
        for product in self:
            product.shopee_linked = bool(product.shopee_item_id)

    def _search_shopee_linked(self, operator, value):
        if operator == "=" and value:
            return [("shopee_item_id", "!=", False)]
        if operator == "=" and not value:
            return [("shopee_item_id", "=", False)]
        if operator == "!=" and value:
            return [("shopee_item_id", "=", False)]
        if operator == "!=" and not value:
            return [("shopee_item_id", "!=", False)]
        return []

    def action_push_shopee_stock(self):
        """Push the selected variants' stock to every stock-push-enabled shop."""
        configs = self.env["shopee.config"].search(
            [("active", "=", True), ("shopee_push_stock", "=", True)]
        )
        if not configs:
            raise UserError(
                "No active Shopee shop connection has 'Push Stock to Shopee' "
                "enabled."
            )
        pushed = 0
        for config in configs:
            pushed += config._push_stock_for_products(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Shopee stock push",
                "message": f"{pushed} update(s) sent to Shopee.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_shopee_stock(self):
        """Pull Shopee stock for all active shop connections."""
        configs = self.env["shopee.config"].search([("active", "=", True)])
        if not configs:
            raise UserError("No active Shopee shop connection was found.")

        updated = 0
        unmapped = 0
        for config in configs:
            updated += config.action_sync_stock()
            unmapped += config.last_stock_sync_unmapped
        message = f"{updated} product(s) updated from Shopee."
        if unmapped:
            message += (
                f" {unmapped} Shopee listing(s) are not linked to an Odoo "
                "product (see Shopee > Product Mappings)."
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Shopee stock sync",
                "message": message,
                "type": "warning" if unmapped else "success",
                "sticky": False,
            },
        }
