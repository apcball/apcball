from odoo import api, fields, models
from odoo.exceptions import UserError

class ShopeeProductMapping(models.Model):
    _name = "shopee.product.mapping"
    _description = "Shopee Product Mapping"
    _order = "shopee_config_id, shopee_sku"
    _check_company_auto = True

    shopee_config_id = fields.Many2one(
        "shopee.config", required=True, ondelete="cascade", index=True, check_company=True
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
        string="Shopee Available Stock",
        help="Available seller stock returned by the most recent Shopee pull. "
        "Editable for reference only: it is not sent to Shopee and the next "
        "Sync Stock overwrites it.",
    )
    last_stock_sync = fields.Datetime(
        string="Last Stock Pull", readonly=True,
    )
    shopee_location_id = fields.Char(
        string="Shopee Stock Location", readonly=True,
        help="Seller stock location (e.g. SGZ) reported by Shopee. Sent back "
        "with every stock push.",
    )
    odoo_free_qty = fields.Integer(
        string="Odoo Warehouse Stock", compute="_compute_odoo_available_stock",
        help="Free-to-use quantity in the shop's stock location / warehouse.",
    )
    use_stock_override = fields.Boolean(string="Manual Stock", copy=False)
    stock_override = fields.Integer(copy=False)
    odoo_available_stock = fields.Integer(
        string="Odoo Available Stock", compute="_compute_odoo_available_stock",
        inverse="_inverse_odoo_available_stock", readonly=False,
        help="Quantity pushed to Shopee: the Odoo warehouse stock, or the "
        "number typed here (manual). Odoo inventory is not changed.",
    )
    refill_below = fields.Integer(
        string="Refill When Shopee Stock Below", default=0,
        help="0 = push whenever the quantity differs. E.g. 10 = automatic push "
        "only once Shopee stock drops below 10; the Odoo available stock is "
        "then sent to Shopee.",
    )
    last_pushed_stock = fields.Integer(readonly=True)
    last_stock_push = fields.Datetime(readonly=True)
    last_pushed_price = fields.Float(readonly=True)
    last_price_push = fields.Datetime(readonly=True)

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

    @api.depends("product_id", "shopee_config_id", "use_stock_override", "stock_override")
    def _compute_odoo_available_stock(self):
        for mapping in self:
            qty = 0
            if mapping.product_id and mapping.shopee_config_id:
                try:
                    context = mapping.shopee_config_id._shopee_stock_context()
                except UserError:
                    context = None
                if context is not None:
                    qty = int(max(mapping.product_id.with_context(**context).free_qty, 0))
            mapping.odoo_free_qty = qty
            mapping.odoo_available_stock = (
                mapping.stock_override if mapping.use_stock_override else qty
            )

    def _inverse_odoo_available_stock(self):
        for mapping in self:
            # The form may send the computed warehouse qty back unchanged
            # (e.g. on create); that is not a manual number.
            if (
                not mapping.use_stock_override
                and mapping.odoo_available_stock == mapping.odoo_free_qty
            ):
                continue
            mapping.write({
                "use_stock_override": True,
                "stock_override": max(mapping.odoo_available_stock, 0),
            })

    def action_reset_stock_override(self):
        self.write({"use_stock_override": False, "stock_override": 0})

    def _shopee_push_qty(self, free_qty):
        """Quantity to send to Shopee: the manual number if set."""
        self.ensure_one()
        return max(self.stock_override, 0) if self.use_stock_override else free_qty

    def action_push_odoo_stock(self):
        pushed = 0
        for config in self.mapped("shopee_config_id"):
            products = self.filtered(
                lambda m: m.shopee_config_id == config and m.product_id and m.active
            ).mapped("product_id")
            if products:
                pushed += config._push_stock_for_products(products=products, force=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Shopee stock push",
                "message": f"{pushed} update(s) sent to Shopee.",
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

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
               model_name=None, location_id=None):
        """Create or refresh a shop listing, even before it is mapped in Odoo."""
        if not sku and not item_id:
            return self.env["shopee.product.mapping"]
        mapping = self.env["shopee.product.mapping"]
        if item_id:
            mapping = self.search([
                ("shopee_config_id", "=", config.id),
                ("shopee_item_id", "=", str(item_id)),
                ("shopee_model_id", "=", str(model_id) if model_id else False),
            ], limit=1)
        if not mapping and sku:
            # Also reuse a mapping entered by hand with only the SKU, otherwise
            # the create below violates config_sku_unique.
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
        if location_id:
            values["shopee_location_id"] = str(location_id)
        if shopee_stock is not None:
            values.update({
                "shopee_stock": int(shopee_stock),
                "last_stock_sync": stock_sync_at or fields.Datetime.now(),
            })
        if mapping:
            mapping.write(values)
            return mapping
        return self.create(dict(values, shopee_config_id=config.id))
