from odoo import api, fields, models

class LazadaProductMapping(models.Model):
    _name = "lazada.product.mapping"
    _description = "Lazada Product Mapping"
    _order = "lazada_config_id, seller_sku"

    lazada_config_id = fields.Many2one(
        "lazada.config", required=True, ondelete="cascade", index=True
    )
    seller_sku = fields.Char(string="Lazada SKU", required=True, index=True)
    lazada_item_id = fields.Char(string="Lazada Item ID", index=True)
    lazada_sku_id = fields.Char(string="Lazada SKU ID", index=True)
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
            "unique(lazada_config_id, seller_sku)",
            "A SKU can only be mapped once per Lazada seller.",
        ),
        (
            "config_model_unique",
            "unique(lazada_config_id, lazada_item_id, lazada_sku_id)",
            "A Lazada item/SKU can only be mapped once per seller.",
        ),
    ]

    @api.model
    def find_product(self, config, item):
        sku_values = [item.get("sku"), item.get("SellerSku")]
        for sku in filter(None, sku_values):
            mapping = self.search([
                ("lazada_config_id", "=", config.id),
                ("seller_sku", "=", str(sku)),
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
        sku_id = item.get("sku_id") or item.get("SkuId")
        mapping = self.search([
            ("lazada_config_id", "=", config.id),
            ("lazada_item_id", "=", str(item_id)) if item_id else ("id", "=", 0),
            ("lazada_sku_id", "=", str(sku_id)) if sku_id else ("lazada_sku_id", "=", False),
            ("active", "=", True),
        ], limit=1)
        return mapping.product_id if mapping else self.env["product.product"]

    @api.model
    def upsert(self, config, sku, product, item_id=None, sku_id=None):
        if not sku or not product:
            return self.env["lazada.product.mapping"]
        mapping = self.search([
            ("lazada_config_id", "=", config.id),
            ("seller_sku", "=", str(sku)),
        ], limit=1)
        values = {
            "lazada_item_id": str(item_id) if item_id else False,
            "lazada_sku_id": str(sku_id) if sku_id else False,
            "product_id": product.id,
            "active": True,
        }
        if mapping:
            mapping.write(values)
            return mapping
        return self.create(dict(
            values, lazada_config_id=config.id, seller_sku=str(sku)
        ))
