import json

from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    lazada_config_id = fields.Many2one(
        "lazada.config", string="Lazada Seller", copy=False, readonly=True,
        index=True,
    )
    lazada_order_id = fields.Char(
        string="Lazada Order ID", copy=False, index=True, readonly=True
    )
    lazada_order_status = fields.Char(readonly=True, copy=False)
    lazada_buyer_id = fields.Char(readonly=True, copy=False)
    lazada_last_status_sync = fields.Datetime(readonly=True, copy=False)
    lazada_payload = fields.Text(readonly=True, copy=False)
    is_lazada_order = fields.Boolean(default=False, copy=False)

    _sql_constraints = [
        (
            "lazada_order_shop_unique",
            "unique(lazada_config_id, lazada_order_id)",
            "A Lazada order can only be imported once per seller.",
        ),
    ]

    @api.model
    def _lazada_find_product(self, item, config=None):
        mapping_model = self.env["lazada.product.mapping"]
        if config:
            product = mapping_model.find_product(config, item)
            if product:
                return product
        Product = self.env["product.product"]
        for sku in (item.get("sku"), item.get("SellerSku")):
            if sku:
                product = Product.search(
                    [("default_code", "=", str(sku))], limit=1
                )
                if product:
                    return product
        for field_name, value in (
            ("lazada_sku_id", item.get("sku_id") or item.get("SkuId")),
            ("lazada_item_id", item.get("item_id") or item.get("ItemId")),
        ):
            if value:
                domain = [(field_name, "=", str(value))]
                if field_name == "lazada_item_id":
                    domain.append(("lazada_sku_id", "=", False))
                product = Product.search(domain, limit=1)
                if product:
                    return product
        placeholder = Product.search(
            [("default_code", "=", "LAZADA_UNMAPPED")], limit=1
        )
        if not placeholder:
            placeholder = Product.create({
                "name": "Lazada - Unmapped Item (fix SKU mapping)",
                "default_code": "LAZADA_UNMAPPED",
                "type": "consu",
            })
        return placeholder

    @staticmethod
    def _lazada_address_note(order, items):
        addr = order.get("address_shipping") or {}
        buyer = " ".join(filter(None, [
            order.get("customer_first_name"), order.get("customer_last_name"),
        ]))
        recipient = " ".join(filter(None, [
            addr.get("first_name"), addr.get("last_name"),
        ]))
        address = " ".join(filter(None, [
            addr.get("address1"), addr.get("address2"), addr.get("address3"),
            addr.get("address4"), addr.get("address5"),
        ]))
        parts = [
            f"Buyer: {buyer or ''}",
            f"Recipient: {recipient or ''}",
            f"Phone: {addr.get('phone') or ''}",
            f"Address: {address or ''}",
            " ".join(filter(None, [
                addr.get("city"), addr.get("region"),
                addr.get("postcode"), addr.get("country"),
            ])),
        ]
        note = "\n".join(p for p in parts if p.strip().rstrip(":"))
        for item in items or []:
            sku = item.get("sku") or item.get("SellerSku")
            if sku:
                note += f"\nSellerSku {sku}: {item.get('name') or ''}".rstrip()
        return note

    @api.model
    def create_from_lazada(self, order_id, partner=None, config=None):
        if not config:
            raise ValueError("A lazada.config is required to import orders.")
        token = config._ensure_valid_token()
        api = config._get_api()
        order = api.get_order(token, str(order_id)) or {}
        items = api.get_order_items(token, str(order_id)) or []
        if not order:
            raise ValueError(f"Lazada order {order_id} was not found.")

        Partner = self.env["res.partner"]
        buyer_name = " ".join(filter(None, [
            order.get("customer_first_name"), order.get("customer_last_name"),
        ])) or "Lazada Buyer"
        if partner is None:
            partner = Partner.find_or_create_lazada_buyer(config, order)
            if not partner and config.customer_partner_id:
                partner = config.customer_partner_id
        if partner is None:
            partner = Partner.search([("name", "=", buyer_name)], limit=1)
            if not partner:
                partner = Partner.create({"name": buyer_name, "customer_rank": 1})

        order_lines = []
        for item in items:
            product = self._lazada_find_product(item, config=config)
            price = item.get("item_price") or item.get("paid_price") or 0
            order_lines.append(fields.Command.create({
                "product_id": product.id,
                "name": item.get("name", product.name),
                "product_uom_qty": item.get("quantity", 1),
                "price_unit": float(price or 0),
            }))

        statuses = order.get("statuses") or []
        values = {
            "partner_id": partner.id,
            "lazada_config_id": config.id,
            "lazada_order_id": str(order_id),
            "lazada_order_status": statuses[0] if statuses else "",
            "lazada_buyer_id": str(
                order.get("customer_email") or buyer_name or ""
            ),
            "lazada_payload": json.dumps(
                {"order": order, "items": items},
                ensure_ascii=False, default=str,
            ),
            "is_lazada_order": True,
            "order_line": order_lines,
            "origin": f"Lazada {order_id}",
            "client_order_ref": buyer_name,
            "note": self._lazada_address_note(order, items) or False,
        }
        return self.create(values)

    def refresh_lazada_status(self, api=None, token=None):
        self.ensure_one()
        config = self.lazada_config_id
        if not config:
            return self
        if api is None:
            token = config._ensure_valid_token()
            api = config._get_api()
        order = api.get_order(token, self.lazada_order_id) or {}
        statuses = order.get("statuses") or []
        if statuses or order:
            self.update_lazada_status(statuses[0] if statuses else "")
        return self

    def update_lazada_status(self, status):
        self.write({
            "lazada_order_status": status,
            "lazada_last_status_sync": fields.Datetime.now(),
        })
