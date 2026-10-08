from odoo import api, fields, models
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = "product.product"

    lazada_linked = fields.Boolean(
        string="Lazada Linked",
        compute="_compute_lazada_linked",
        search="_search_lazada_linked",
        help="True if this variant is linked to a Lazada item/SKU.",
    )
    lazada_item_id = fields.Char(
        string="Lazada Item ID", readonly=True, copy=False
    )
    lazada_sku_id = fields.Char(
        string="Lazada SKU ID",
        readonly=True,
        copy=False,
        help="Lazada SKU (variant) id. Empty for single-SKU products.",
    )
    lazada_stock = fields.Integer(
        string="Lazada Available Stock",
        readonly=True,
        copy=False,
        help="Stock quantity as last reported by Lazada. Reference only - "
        "not synced back into Odoo's own inventory.",
    )
    lazada_last_sync = fields.Datetime(
        string="Lazada Last Stock Sync", readonly=True, copy=False
    )
    lazada_sync_stock_out = fields.Boolean(
        string="Push Stock to Lazada",
        default=True,
        copy=False,
        help="When enabled and the seller connection has stock push turned "
        "on, this variant's Odoo free-to-use quantity is pushed to Lazada.",
    )
    lazada_pushed_stock = fields.Integer(
        string="Lazada Last Pushed Stock", readonly=True, copy=False,
        help="Last quantity sent to Lazada. Used to skip unchanged pushes.",
    )
    lazada_stock_push_date = fields.Datetime(
        string="Lazada Last Stock Push", readonly=True, copy=False
    )
    lazada_sync_price_out = fields.Boolean(
        string="Push Price to Lazada",
        default=False,
        copy=False,
        help="When enabled and the seller connection has price push turned "
        "on, this variant's Odoo sales price is pushed to Lazada. Off by "
        "default - price pushes are higher-risk than stock pushes.",
    )
    lazada_price = fields.Float(
        string="Lazada Price",
        readonly=True,
        copy=False,
        help="Price as last reported/pushed to Lazada. Reference only.",
    )
    lazada_pushed_price = fields.Float(
        string="Lazada Last Pushed Price", readonly=True, copy=False,
        help="Last price sent to Lazada. Used to skip unchanged pushes.",
    )
    lazada_price_push_date = fields.Datetime(
        string="Lazada Last Price Push", readonly=True, copy=False
    )

    @api.depends("lazada_item_id")
    def _compute_lazada_linked(self):
        for product in self:
            product.lazada_linked = bool(product.lazada_item_id)

    def _search_lazada_linked(self, operator, value):
        if operator == "=" and value:
            return [("lazada_item_id", "!=", False)]
        if operator == "=" and not value:
            return [("lazada_item_id", "=", False)]
        if operator == "!=" and value:
            return [("lazada_item_id", "=", False)]
        if operator == "!=" and not value:
            return [("lazada_item_id", "!=", False)]
        return []

    def action_push_lazada_stock(self):
        """Push the selected variants' stock to every stock-push-enabled seller."""
        configs = self.env["lazada.config"].search(
            [("active", "=", True), ("lazada_push_stock", "=", True)]
        )
        if not configs:
            raise UserError(
                "No active Lazada seller connection has 'Push Stock to "
                "Lazada' enabled."
            )
        pushed = 0
        for config in configs:
            pushed += config._push_stock_for_products(self)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lazada stock push",
                "message": f"{pushed} update(s) sent to Lazada.",
                "type": "success",
                "sticky": False,
            },
        }

    def action_sync_lazada_stock(self):
        """Pull Lazada stock for all active seller connections."""
        configs = self.env["lazada.config"].search([("active", "=", True)])
        if not configs:
            raise UserError("No active Lazada seller connection was found.")

        updated = 0
        unmapped = 0
        for config in configs:
            updated += config.action_sync_stock()
            unmapped += config.last_stock_sync_unmapped
        message = f"{updated} product(s) updated from Lazada."
        if unmapped:
            message += (
                f" {unmapped} Lazada listing(s) are not linked to an Odoo "
                "product (see Lazada > Product Mappings)."
            )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lazada stock sync",
                "message": message,
                "type": "warning" if unmapped else "success",
                "sticky": False,
            },
        }
