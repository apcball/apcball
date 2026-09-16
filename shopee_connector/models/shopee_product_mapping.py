from odoo import api, fields, models

class ShopeeProductMapping(models.Model):
    _name = "shopee.product.mapping"
    _description = "Shopee Product Mapping"
    _order = "shopee_config_id, shopee_sku"

    shopee_config_id = fields.Many2one(
        "shopee.config", required=True, ondelete="cascade", index=True
    )
    shopee_sku = fields.Char(string="Shopee SKU", required=True, index=True)
    shopee_item_id = fields.Char(string="Shopee Item ID", index=True)
    shopee_model_id = fields.Char(string="Shopee Model ID", index=True)
    product_id = fields.Many2one(
        "product.product", string="Odoo Product", required=True,
        ondelete="restrict",
    )
    active = fields.Boolean(default=True)
    last_pushed_stock = fields.Integer(readonly=True)
    last_stock_push = fields.Datetime(readonly=True)

    _sql_constraints = [
        (
            "config_sku_unique",
            "unique(shopee_config_id, shopee_sku)",
            "A SKU can only be mapped once per Shopee shop.",
        ),
        (
            "config_model_unique",
            "unique(shopee_config_id, shopee_item_id, shopee_model_id)",
            "A Shopee item/model can only be mapped once per shop.",
        ),
    ]

    @api.model
    def find_product(self, config, item):
        sku_values = [item.get("model_sku"), item.get("item_sku")]
        for sku in filter(None, sku_values):
            mapping = self.search([
                ("shopee_config_id", "=", config.id),
                ("shopee_sku", "=", str(sku)),
                ("active", "=", True),
            ], limit=1)
            if mapping:
                return mapping.product_id
            product = self.env["product.product"].search(
                [("default_code", "=", str(sku))], limit=1
            )
            if product:
                return product
        item_id = item.get("item_id")
        model_id = item.get("model_id")
        mapping = self.search([
            ("shopee_config_id", "=", config.id),
            ("shopee_item_id", "=", str(item_id)) if item_id else ("id", "=", 0),
            ("shopee_model_id", "=", str(model_id)) if model_id else ("shopee_model_id", "=", False),
            ("active", "=", True),
        ], limit=1)
        return mapping.product_id if mapping else self.env["product.product"]

    @api.model
    def upsert(self, config, sku, product, item_id=None, model_id=None):
        if not sku or not product:
            return self.env["shopee.product.mapping"]
        mapping = self.search([
            ("shopee_config_id", "=", config.id),
            ("shopee_sku", "=", str(sku)),
        ], limit=1)
        values = {
            "shopee_item_id": str(item_id) if item_id else False,
            "shopee_model_id": str(model_id) if model_id else False,
            "product_id": product.id,
            "active": True,
        }
        if mapping:
            mapping.write(values)
            return mapping
        return self.create(dict(values, shopee_config_id=config.id, shopee_sku=str(sku)))
