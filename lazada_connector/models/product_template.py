from odoo import fields, models
from odoo.exceptions import UserError


class ProductProduct(models.Model):
    _inherit = "product.product"

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
        for config in configs:
            updated += config.action_sync_stock()

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lazada stock sync",
                "message": f"{updated} product(s) updated from Lazada.",
                "type": "success",
                "sticky": False,
            },
        }
