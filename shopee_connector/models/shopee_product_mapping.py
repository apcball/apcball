from odoo import api, fields, models

class ShopeeProductMapping(models.Model):
    _name = "shopee.product.mapping"
    _description = "Shopee Product Mapping"
    _order = "shopee_config_id, shopee_sku"

    shopee_config_id = fields.Many2one(
        "shopee.config", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one(
        "res.company", related="shopee_config_id.company_id", store=True,
        readonly=True, index=True,
    )
    shopee_sku = fields.Char(string="Shopee SKU", index=True)
    shopee_item_id = fields.Char(string="Shopee Item ID", index=True)
    shopee_model_id = fields.Char(string="Shopee Model ID", index=True)
    shopee_item_name = fields.Char(string="Shopee Item Name", readonly=True)
    shopee_model_name = fields.Char(string="Shopee Variant", readonly=True)
    product_id = fields.Many2one(
        "product.product", string="Odoo Product",
        ondelete="restrict", check_company=True,
    )
    odoo_sku = fields.Char(
        related="product_id.default_code", string="Odoo SKU", readonly=True,
    )
    active = fields.Boolean(default=True)
    shopee_stock = fields.Integer(
        string="Shopee Available Stock", readonly=True,
        help="Available seller stock returned by the most recent Shopee pull.",
    )
    last_stock_sync = fields.Datetime(
        string="Last Stock Pull", readonly=True,
    )
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
    def find_product_by_sku(self, sku):
        """Return one Odoo variant for a Shopee SKU, without guessing matches."""
        normalized_sku = str(sku or "").strip()
        if not normalized_sku:
            return self.env["product.product"]
        Product = self.env["product.product"]
        products = Product.search(
            [("default_code", "=", normalized_sku)], limit=2
        )
        if len(products) == 1:
            return products
        # Shopee users often enter an upper-case SKU while the Odoo product
        # code contains lower-case characters.  Accept it only if unique.
        products = Product.search(
            [("default_code", "=ilike", normalized_sku)], limit=20
        ).filtered(
            lambda product: (product.default_code or "").strip().casefold()
            == normalized_sku.casefold()
        )
        return products if len(products) == 1 else Product

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
            product = self.find_product_by_sku(sku)
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
    def upsert(self, config, sku=None, product=None, item_id=None, model_id=None,
               shopee_stock=None, stock_sync_at=None, item_name=None,
               model_name=None):
        """Create or refresh a shop listing, even before it is mapped in Odoo."""
        if not sku and not item_id:
            return self.env["shopee.product.mapping"]
        if item_id:
            mapping = self.search([
                ("shopee_config_id", "=", config.id),
                ("shopee_item_id", "=", str(item_id)),
                ("shopee_model_id", "=", str(model_id) if model_id else False),
            ], limit=1)
        else:
            mapping = self.search([
                ("shopee_config_id", "=", config.id),
                ("shopee_sku", "=", str(sku)),
            ], limit=1)
        values = {
            "shopee_item_id": str(item_id) if item_id else False,
            "shopee_model_id": str(model_id) if model_id else False,
            "shopee_item_name": item_name or False,
            "shopee_model_name": model_name or False,
            "active": True,
        }
        if sku:
            values["shopee_sku"] = str(sku)
        if product:
            values["product_id"] = product.id
        if shopee_stock is not None:
            values.update({
                "shopee_stock": int(shopee_stock),
                "last_stock_sync": stock_sync_at or fields.Datetime.now(),
            })
        if mapping:
            mapping.write(values)
            return mapping
        return self.create(dict(values, shopee_config_id=config.id))
