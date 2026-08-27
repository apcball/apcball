from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    shopee_order_sn = fields.Char(
        string="Shopee Order SN", copy=False, index=True, readonly=True
    )
    shopee_order_status = fields.Char(readonly=True, copy=False)
    is_shopee_order = fields.Boolean(default=False, copy=False)

    @api.model
    def _shopee_find_product(self, item):
        """Resolve a Shopee order item dict to a product.product.

        Match order: model_sku -> item_sku -> shopee_model_id -> shopee_item_id
        -> SHOPEE_UNMAPPED placeholder.
        """
        Product = self.env["product.product"]
        for sku in (item.get("model_sku"), item.get("item_sku")):
            if sku:
                product = Product.search([("default_code", "=", sku)], limit=1)
                if product:
                    return product
        model_id = item.get("model_id")
        if model_id:
            product = Product.search(
                [("shopee_model_id", "=", str(model_id))], limit=1
            )
            if product:
                return product
        item_id = item.get("item_id")
        if item_id:
            product = Product.search(
                [("shopee_item_id", "=", str(item_id)),
                 ("shopee_model_id", "=", False)], limit=1
            )
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
                addr.get("district"), addr.get("city"),
                addr.get("state"), addr.get("zipcode"), addr.get("region"),
            ])),
        ]
        return "\n".join(p for p in parts if p.strip().rstrip(":"))

    @api.model
    def create_from_shopee(self, shopee_order, partner=None):
        """Create a draft sale.order from a Shopee get_order_detail() dict.
        Does not confirm, invoice, or push anything back to Shopee.

        ``partner`` is the res.partner to bill/ship to (normally the shop
        connection's Marketplace Customer). If omitted, falls back to a
        partner matched by buyer_username (kept for tests / simple setups).
        """
        Partner = self.env["res.partner"]

        buyer_name = shopee_order.get("buyer_username") or "Shopee Buyer"
        if partner is None:
            partner = Partner.search([("name", "=", buyer_name)], limit=1)
            if not partner:
                partner = Partner.create({"name": buyer_name})

        order_lines = []
        for item in shopee_order.get("item_list", []):
            product = self._shopee_find_product(item)
            price = (
                item.get("model_discounted_price")
                or item.get("model_original_price")
                or 0
            )
            qty = item.get("model_quantity_purchased", 1)
            order_lines.append(
                fields.Command.create({
                    "product_id": product.id,
                    "name": item.get("item_name", product.name),
                    "product_uom_qty": qty,
                    "price_unit": price,
                })
            )

        order = self.create({
            "partner_id": partner.id,
            "shopee_order_sn": shopee_order["order_sn"],
            "shopee_order_status": shopee_order.get("order_status", ""),
            "is_shopee_order": True,
            "order_line": order_lines,
            "origin": f"Shopee {shopee_order['order_sn']}",
            "client_order_ref": buyer_name,
            "note": self._shopee_address_note(shopee_order) or False,
        })
        return order
