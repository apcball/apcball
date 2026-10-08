from odoo import api, fields, models
from odoo.exceptions import UserError

class LazadaProductMapping(models.Model):
    _name = "lazada.product.mapping"
    _description = "Lazada Product Mapping"
    _order = "lazada_config_id, seller_sku"
    _check_company_auto = True

    lazada_config_id = fields.Many2one(
        "lazada.config", required=True, ondelete="cascade", index=True, check_company=True
    )
    company_id = fields.Many2one(
        "res.company", related="lazada_config_id.company_id", store=True,
        readonly=True, index=True,
    )
    seller_sku = fields.Char(string="Lazada SKU", required=True, index=True)
    lazada_item_id = fields.Char(string="Lazada Item ID", index=True)
    lazada_sku_id = fields.Char(string="Lazada SKU ID", index=True)
    lazada_item_name = fields.Char(string="Lazada Item Name", readonly=True)
    lazada_sku_name = fields.Char(string="Lazada Variant", readonly=True)
    product_id = fields.Many2one(
        "product.product", string="Odoo Product",
        ondelete="restrict", check_company=True,
    )
    odoo_sku = fields.Char(
        related="product_id.default_code", string="Internal Reference", readonly=True,
    )
    active = fields.Boolean(default=True)
    lazada_stock = fields.Integer(
        string="Lazada Available Stock",
        help="Available stock returned by the most recent Lazada pull. "
        "Editable for reference only: it is not sent to Lazada and the next "
        "Sync Stock overwrites it.",
    )
    last_stock_sync = fields.Datetime(
        string="Last Stock Pull", readonly=True,
    )
    odoo_free_qty = fields.Integer(
        string="Odoo Warehouse Stock", compute="_compute_odoo_available_stock",
        help="Free-to-use quantity in the seller's stock location / warehouse.",
    )
    use_stock_override = fields.Boolean(string="Manual Stock", copy=False)
    stock_override = fields.Integer(copy=False)
    odoo_available_stock = fields.Integer(
        string="Odoo Available Stock", compute="_compute_odoo_available_stock",
        inverse="_inverse_odoo_available_stock", readonly=False,
        help="Quantity pushed to Lazada: the Odoo warehouse stock, or the "
        "number typed here (manual). Odoo inventory is not changed.",
    )
    refill_below = fields.Integer(
        string="Refill When Lazada Stock Below", default=0,
        help="0 = push whenever the quantity differs. E.g. 10 = automatic push "
        "only once Lazada stock drops below 10; the Odoo available stock is "
        "then sent to Lazada.",
    )
    last_pushed_stock = fields.Integer(readonly=True)
    last_stock_push = fields.Datetime(readonly=True)
    last_pushed_price = fields.Float(readonly=True)
    last_price_push = fields.Datetime(readonly=True)

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

    @api.depends("product_id", "lazada_config_id", "use_stock_override", "stock_override")
    def _compute_odoo_available_stock(self):
        for mapping in self:
            qty = 0
            if mapping.product_id and mapping.lazada_config_id:
                try:
                    context = mapping.lazada_config_id._lazada_stock_context()
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

    def _lazada_push_qty(self, free_qty):
        """Quantity to send to Lazada: the manual number if set."""
        self.ensure_one()
        return max(self.stock_override, 0) if self.use_stock_override else free_qty

    def action_push_odoo_stock(self):
        pushed = 0
        for config in self.mapped("lazada_config_id"):
            products = self.filtered(
                lambda m: m.lazada_config_id == config and m.product_id and m.active
            ).mapped("product_id")
            if products:
                pushed += config._push_stock_for_products(products=products, force=True)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lazada stock push",
                "message": f"{pushed} update(s) sent to Lazada.",
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    @api.model
    def find_product_by_sku(self, sku):
        """Return one Odoo variant for a Lazada SKU, without guessing matches."""
        normalized_sku = str(sku or "").strip()
        if not normalized_sku:
            return self.env["product.product"]
        Product = self.env["product.product"]
        products = Product.search(
            [("default_code", "=", normalized_sku)], limit=2
        )
        if len(products) == 1:
            return products
        # Lazada users often enter an upper-case SKU while the Odoo product
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
        sku_values = [item.get("sku"), item.get("SellerSku")]
        for sku in filter(None, sku_values):
            mapping = self.search([
                ("lazada_config_id", "=", config.id),
                ("seller_sku", "=", str(sku)),
                ("active", "=", True),
            ], limit=1)
            if mapping.product_id:
                return mapping.product_id
            product = self.find_product_by_sku(sku)
            if product:
                return product
        item_id = item.get("item_id") or item.get("product_id")
        sku_id = item.get("sku_id") or item.get("SkuId")
        mapping = self.search([
            ("lazada_config_id", "=", config.id),
            ("lazada_item_id", "=", str(item_id)) if item_id else ("id", "=", 0),
            ("lazada_sku_id", "=", str(sku_id)) if sku_id else ("lazada_sku_id", "=", False),
            ("active", "=", True),
        ], limit=1)
        return mapping.product_id if mapping else self.env["product.product"]

    @api.model
    def upsert(self, config, sku, product=None, item_id=None, sku_id=None,
               lazada_stock=None, stock_sync_at=None, item_name=None,
               sku_name=None):
        """Create or refresh a seller listing, even before it is mapped in Odoo."""
        if not sku:
            return self.env["lazada.product.mapping"]
        Mapping = self.with_context(active_test=False)
        mapping = Mapping.search([
            ("lazada_config_id", "=", config.id),
            ("seller_sku", "=", str(sku)),
        ], limit=1)
        if not mapping and item_id and sku_id:
            # The SellerSku was renamed on Lazada: keep the same listing row.
            mapping = Mapping.search([
                ("lazada_config_id", "=", config.id),
                ("lazada_item_id", "=", str(item_id)),
                ("lazada_sku_id", "=", str(sku_id)),
            ], limit=1)
        values = {
            "seller_sku": str(sku),
            "lazada_item_id": str(item_id) if item_id else False,
            "lazada_sku_id": str(sku_id) if sku_id else False,
            "lazada_item_name": item_name or False,
            "lazada_sku_name": sku_name or False,
            "active": True,
        }
        if product:
            values["product_id"] = product.id
        if lazada_stock is not None:
            values.update({
                "lazada_stock": int(lazada_stock),
                "last_stock_sync": stock_sync_at or fields.Datetime.now(),
            })
        if mapping:
            mapping.write(values)
            return mapping
        return self.create(dict(values, lazada_config_id=config.id))
