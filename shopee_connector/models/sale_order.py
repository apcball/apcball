import json

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    shopee_config_id = fields.Many2one(
        "shopee.config", string="Shopee Shop", copy=False, readonly=True,
        index=True,
    )
    shopee_order_sn = fields.Char(
        string="Shopee Order SN", copy=False, index=True, readonly=True
    )
    shopee_order_status = fields.Char(readonly=True, copy=False)
    shopee_buyer_id = fields.Char(readonly=True, copy=False)
    shopee_last_status_sync = fields.Datetime(readonly=True, copy=False)
    shopee_payload = fields.Text(readonly=True, copy=False)
    is_shopee_order = fields.Boolean(default=False, copy=False)

    _sql_constraints = [
        (
            "shopee_order_shop_unique",
            "unique(shopee_config_id, shopee_order_sn)",
            "A Shopee order can only be imported once per shop.",
        ),
    ]

    @api.model
    def _shopee_find_product(self, item, config=None):
        mapping_model = self.env["shopee.product.mapping"]
        if config:
            product = mapping_model.find_product(config, item)
            if product:
                return product
        Product = self.env["product.product"]
        for sku in (item.get("model_sku"), item.get("item_sku")):
            if sku:
                product = Product.search([("default_code", "=", str(sku))], limit=1)
                if product:
                    return product
        for field_name, value in (
            ("shopee_model_id", item.get("model_id")),
            ("shopee_item_id", item.get("item_id")),
        ):
            if value:
                domain = [(field_name, "=", str(value))]
                if field_name == "shopee_item_id":
                    domain.append(("shopee_model_id", "=", False))
                product = Product.search(domain, limit=1)
                if product:
                    return product
        placeholder = Product.search(
            [("default_code", "=", "SHOPEE_UNMAPPED")], limit=1
        )
        if not placeholder:
            placeholder = Product.create({
                "name": "Shopee - Unmapped Item (fix SKU mapping)",
                "default_code": "SHOPEE_UNMAPPED",
                "type": "consu",
            })
        return placeholder

    @staticmethod
    def _shopee_address_note(shopee_order):
        addr = shopee_order.get("recipient_address") or {}
        if not addr:
            return ""
        parts = [
            f"Buyer: {shopee_order.get('buyer_username') or ''}",
            f"Recipient: {addr.get('name') or ''}",
            f"Phone: {addr.get('phone') or ''}",
            f"Address: {addr.get('full_address') or ''}",
            " ".join(filter(None, [
                addr.get("district"), addr.get("city"), addr.get("state"),
                addr.get("zipcode"), addr.get("region"),
            ])),
        ]
        return "\n".join(p for p in parts if p.strip().rstrip(":"))

    @api.model
    def create_from_shopee(self, shopee_order, partner=None, config=None):
        Partner = self.env["res.partner"]
        buyer_name = shopee_order.get("buyer_username") or "Shopee Buyer"
        if partner is None and config:
            partner = Partner.find_or_create_shopee_buyer(config, shopee_order)
            if not partner and config.customer_partner_id:
                partner = config.customer_partner_id
        if partner is None:
            partner = Partner.search([("name", "=", buyer_name)], limit=1)
            if not partner:
                partner = Partner.create({"name": buyer_name, "customer_rank": 1})

        order_lines = []
        for item in shopee_order.get("item_list", []):
            product = self._shopee_find_product(item, config=config)
            price = (
                item.get("model_discounted_price")
                or item.get("model_original_price")
                or item.get("item_price")
                or 0
            )
            order_lines.append(fields.Command.create({
                "product_id": product.id,
                "name": item.get("item_name", product.name),
                "product_uom_qty": item.get("model_quantity_purchased", 1),
                "price_unit": price,
            }))

        values = {
            "partner_id": partner.id,
            "shopee_config_id": config.id if config else False,
            "shopee_order_sn": shopee_order["order_sn"],
            "shopee_order_status": shopee_order.get("order_status", ""),
            "shopee_buyer_id": str(
                shopee_order.get("buyer_user_id")
                or shopee_order.get("buyer_username")
                or ""
            ),
            "shopee_payload": json.dumps(
                shopee_order, ensure_ascii=False, default=str
            ),
            "is_shopee_order": True,
            "order_line": order_lines,
            "origin": f"Shopee {shopee_order['order_sn']}",
            "client_order_ref": buyer_name,
            "note": self._shopee_address_note(shopee_order) or False,
        }
        return self.create(values)

    def update_shopee_status(self, status):
        self.write({
            "shopee_order_status": status,
            "shopee_last_status_sync": fields.Datetime.now(),
        })
