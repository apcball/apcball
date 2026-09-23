import json
import logging
from html import escape
from datetime import datetime, time, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PAYMENT_SOURCES = [("excel", "Seller Center export"), ("escrow", "Shopee API")]


class SaleOrder(models.Model):
    _inherit = "sale.order"

    shopee_config_id = fields.Many2one(
        "shopee.config", string="Shopee Shop", copy=False, readonly=True,
        index=True, check_company=True,
    )
    shopee_order_sn = fields.Char(
        string="Shopee Order SN", copy=False, index=True, readonly=True
    )
    shopee_order_status = fields.Char(readonly=True, copy=False)
    shopee_buyer_id = fields.Char(readonly=True, copy=False)
    shopee_last_status_sync = fields.Datetime(readonly=True, copy=False)
    shopee_payload = fields.Text(readonly=True, copy=False)
    is_shopee_order = fields.Boolean(default=False, copy=False)
    shopee_net_income = fields.Monetary(
        string="Shopee Order Income", readonly=True, copy=False,
        help="What Shopee pays the shop for this order after its fees.",
    )
    shopee_payment_source = fields.Selection(
        PAYMENT_SOURCES, readonly=True, copy=False,
    )

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
                product = Product.search([("default_code", "=", str(sku))], limit=2)
                if len(product) > 1:
                    raise UserError(f"Shopee SKU {sku} matches multiple products. Set an explicit shop mapping.")
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

    @api.model
    def _shopee_trade_channel_values(self):
        """{'trade_channel': 'shopee'} when marketplace_settlement is installed.

        The field and its choices live in another addon, so only set it if
        this database actually has it and offers the 'shopee' channel.
        """
        field = self._fields.get("trade_channel")
        if not field or field.type != "selection":
            return {}
        if "shopee" not in field.get_values(self.env):
            return {}
        return {"trade_channel": "shopee"}

    @api.model
    def _shopee_backfill_trade_channel(self):
        """Set Trade Channel = Shopee on imported orders that have none."""
        values = self._shopee_trade_channel_values()
        if not values:
            return 0
        orders = self.with_context(active_test=False).search([
            ("is_shopee_order", "=", True),
            ("trade_channel", "=", False),
        ])
        orders.write(values)
        return len(orders)

    @staticmethod
    def _shopee_address_note(shopee_order):
        buyer = escape(str(shopee_order.get("buyer_username") or ""))
        return f"<p>Shopee buyer: {buyer}</p>" if buyer else ""

    @api.model
    def create_from_shopee(self, shopee_order, partner=None, config=None):
        if config:
            self = self.with_company(config.company_id).with_context(
                allowed_company_ids=[config.company_id.id],
            )
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
            # A free/promotional item has a legitimate discounted price of zero.
            price = next((item[key] for key in (
                "model_discounted_price", "model_original_price", "item_price",
            ) if item.get(key) is not None), 0)
            order_lines.append(fields.Command.create({
                "product_id": product.id,
                "name": item.get("item_name", product.name),
                "product_uom_qty": item.get("model_quantity_purchased", 1),
                "price_unit": self._shopee_price_ex_vat(price, config),
            }))

        values = {
            "company_id": config.company_id.id if config else self.env.company.id,
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
            "client_order_ref": shopee_order["order_sn"],
            "note": self._shopee_address_note(shopee_order) or False,
        }
        values.update(self._shopee_trade_channel_values())
        commitment = self._shopee_commitment_date(shopee_order.get("pay_time"), config)
        if commitment:
            values["commitment_date"] = commitment
        order = self.create(values)
        order._shopee_cancel_if_cancelled()
        return order

    @api.model
    def _shopee_price_ex_vat(self, price, config=None):
        """Shopee prices include VAT; remove the configured rate (7%)."""
        rate = config.shopee_price_vat_rate if config else 0.0
        if not price or not rate:
            return price
        return price / (1 + rate / 100.0)

    @api.model
    def _shopee_local_tz(self):
        return pytz.timezone(self.env.user.tz or "Asia/Bangkok")

    @api.model
    def _shopee_commitment_date(self, paid_at, config=None):
        """Delivery Date from the payment time and the shop's cut-off.

        ``paid_at``: Shopee unix timestamp, or a timezone-aware datetime.
        Paid before the cut-off (default 14:00) ships that day, otherwise
        the next day. Returns a naive UTC datetime at the cut-off time.
        """
        if not paid_at or not config:
            return False
        tz = self._shopee_local_tz()
        if isinstance(paid_at, datetime):
            local = paid_at.astimezone(tz)
        else:
            local = datetime.fromtimestamp(int(paid_at), tz)
        cutoff = config.shopee_ship_cutoff_hour or 14.0
        hours, minutes = int(cutoff), int(round((cutoff % 1) * 60))
        ship_day = local.date()
        if (local.hour, local.minute) >= (hours, minutes):
            ship_day += timedelta(days=1)
        ship_at = tz.localize(datetime.combine(ship_day, time(hours, minutes)))
        return ship_at.astimezone(pytz.utc).replace(tzinfo=None)

    def _shopee_set_commitment_date(self, paid_at):
        """Fill Delivery Date once the payment time is known."""
        for order in self.filtered(lambda o: not o.commitment_date and o.state != "cancel"):
            commitment = order._shopee_commitment_date(paid_at, order.shopee_config_id)
            if commitment:
                order.commitment_date = commitment

    # ------------------------------------------------------------------
    # Payment details (shipping, shop voucher, Shopee fees)
    # ------------------------------------------------------------------
    def _shopee_service_product(self, config, field_name, code, name):
        """Configured product, else by Internal Reference, else create one."""
        product = config[field_name] if config else self.env["product.product"]
        if product:
            return product
        Product = self.env["product.product"]
        if code:
            product = Product.search([("default_code", "=ilike", code)], limit=1)
        if not product:
            product = Product.sudo().create({
                "name": name,
                "default_code": code or False,
                "detailed_type": "service",
                "sale_ok": True,
                "purchase_ok": False,
                "invoice_policy": "order",
            })
        if config:
            config.sudo()[field_name] = product
        return product

    def _shopee_payment_lines(self, payment):
        config = self.shopee_config_id
        lines = []
        if payment.get("shipping"):
            product = self._shopee_service_product(
                config, "shopee_shipping_product_id", "Service04", "ค่าขนส่ง",
            )
            lines.append({
                "shopee_line_type": "shipping",
                "product_id": product.id,
                "name": product.display_name,
                "product_uom_qty": 1,
                "price_unit": self._shopee_price_ex_vat(payment["shipping"], config),
                "sequence": 9000,
            })
        if payment.get("voucher_amount"):
            codes = payment.get("voucher_codes") or []
            Product = self.env["product.product"]
            product = Product.search(
                [("default_code", "in", codes)], limit=1,
            ) if codes else Product
            if not product:
                product = self._shopee_service_product(
                    config, "shopee_voucher_product_id", False,
                    "Shopee Seller Voucher",
                )
            label = "โค้ดส่วนลดร้านค้าจากผู้ขาย"
            if codes:
                label += " - " + ", ".join(codes)
            lines.append({
                "shopee_line_type": "voucher",
                "product_id": product.id,
                "name": label,
                "product_uom_qty": 1,
                "price_unit": -self._shopee_price_ex_vat(
                    payment["voucher_amount"], config,
                ),
                "sequence": 9001,
            })
        return lines

    def _shopee_payment_note(self, payment):
        """Summary like Seller Center's payment details (fees included)."""
        def money(value):
            return f"฿{value:,.2f}"

        rows = [("รวมค่าสินค้า", payment.get("products_total"))]
        rows.append(("ค่าจัดส่งที่ชำระโดยผู้ซื้อ", payment.get("shipping")))
        if payment.get("voucher_amount"):
            label = "โค้ดส่วนลดร้านค้าจากผู้ขาย"
            if payment.get("voucher_codes"):
                label += " - " + ", ".join(payment["voucher_codes"])
            rows.append((label, -payment["voucher_amount"]))
        fees = [
            ("ค่าคอมมิชชั่น", payment.get("commission")),
            ("ค่าบริการ", payment.get("service_fee")),
            ("ค่าธรรมเนียมโครงสร้างพื้นฐานแพลตฟอร์ม", payment.get("infra_fee")),
            ("ค่าธุรกรรมการชำระเงิน", payment.get("transaction_fee")),
        ]
        fee_total = sum(v or 0.0 for _label, v in fees)
        if fee_total:
            rows.append(("ค่าธรรมเนียม", -fee_total))
            rows += [(f"&nbsp;&nbsp;{label}", -v) for label, v in fees if v]
        body = "".join(
            f"<tr><td>{label}</td><td style='text-align:right'>{money(value)}</td></tr>"
            for label, value in rows if value is not None
        )
        net = payment.get("net_income")
        if net is not None:
            body += (
                "<tr><td><b>รายรับจากคำสั่งซื้อ</b></td>"
                f"<td style='text-align:right'><b>{money(net)}</b></td></tr>"
            )
        buyer = self._shopee_address_note(json.loads(self.shopee_payload or "{}"))
        source = dict(PAYMENT_SOURCES).get(payment.get("source"), "")
        return (
            f"{buyer}<p><b>Shopee payment details</b> ({escape(source)})</p>"
            f"<table>{body}</table>"
        )

    def _shopee_apply_payment(self, payment):
        """Add shipping / shop voucher lines and the fee summary.

        Only quotations are changed; lines added earlier are replaced so the
        data can be re-applied (Excel re-import, API sync).
        """
        self.ensure_one()
        if self.state not in ("draft", "sent"):
            return False
        commands = [
            fields.Command.delete(line.id)
            for line in self.order_line.filtered("shopee_line_type")
        ]
        commands += [
            fields.Command.create(vals) for vals in self._shopee_payment_lines(payment)
        ]
        self.write({
            "order_line": commands,
            "note": self._shopee_payment_note(payment),
            "shopee_net_income": payment.get("net_income") or 0.0,
            "shopee_payment_source": payment.get("source"),
        })
        return True

    @api.model
    def _shopee_payment_from_escrow(self, response, detail=None):
        income = (response or {}).get("response", {}).get("order_income") or {}
        if not income:
            return False

        def num(key):
            try:
                return float(income.get(key) or 0.0)
            except (TypeError, ValueError):
                return 0.0

        items = (detail or {}).get("item_list") or []
        products_total = sum(
            float(i.get("model_discounted_price") or 0)
            * float(i.get("model_quantity_purchased") or 1)
            for i in items
        ) or num("order_selling_price") or num("original_price")
        codes = income.get("seller_voucher_code") or []
        if isinstance(codes, str):
            codes = [codes]
        return {
            "source": "escrow",
            "products_total": products_total,
            "shipping": num("buyer_paid_shipping_fee"),
            "voucher_amount": num("voucher_from_seller"),
            "voucher_codes": [c for c in codes if c],
            "commission": num("commission_fee"),
            "service_fee": num("service_fee"),
            "infra_fee": num("platform_fee") or None,
            "transaction_fee": num("seller_transaction_fee"),
            "net_income": num("escrow_amount"),
        }

    def _shopee_fetch_escrow(self, api, token, detail=None):
        """Best effort: Shopee may refuse escrow data for unpaid orders."""
        for order in self:
            if (
                order.shopee_payment_source == "escrow"
                or order.state not in ("draft", "sent")
                or order.shopee_order_status in ("UNPAID", "CANCELLED", "")
            ):
                continue
            try:
                response = api.get_escrow_detail(token, order.shopee_order_sn)
            except Exception as exc:  # noqa: BLE001 - optional data
                _logger.warning("Shopee escrow %s: %s", order.shopee_order_sn, exc)
                continue
            payment = self._shopee_payment_from_escrow(
                response, detail or json.loads(order.shopee_payload or "{}"),
            )
            if payment:
                order._shopee_apply_payment(payment)

    def _shopee_cancel_if_cancelled(self):
        """React to a Shopee order that became CANCELLED.

        Draft/sent quotations are cancelled outright. A confirmed sales order
        may already have deliveries or invoices, so it is left alone and only
        tagged for staff to review manually.
        """
        cancelled = self.filtered(lambda order: order.shopee_order_status == "CANCELLED")
        to_cancel = cancelled.filtered(lambda order: order.state in ("draft", "sent"))
        if to_cancel:
            to_cancel._action_cancel()
        confirmed_cancelled = cancelled - to_cancel
        confirmed_cancelled = confirmed_cancelled.filtered(lambda order: order.state != "cancel")
        if confirmed_cancelled:
            confirmed_cancelled.write({
                "tag_ids": [fields.Command.link(
                    self.env.ref("shopee_connector.tag_cancelled_after_confirm").id
                )],
            })
        return to_cancel

    def apply_shopee_detail(self, detail):
        """Refresh status and buyer contact from a get_order_detail entry.

        Shopee masks the recipient until the order is paid, so the address
        is often only available on a later sync.
        """
        for order in self:
            order._shopee_apply_recipient(detail)
        self._shopee_set_commitment_date(detail.get("pay_time"))
        self.update_shopee_status(detail.get("order_status", ""))

    def _shopee_apply_recipient(self, detail):
        """Update the buyer / delivery address from the order's recipient."""
        self.ensure_one()
        partner = self.partner_id
        if not partner.shopee_config_id or partner.shopee_config_id != self.shopee_config_id:
            return False
        shipping = partner._shopee_update_from_order(detail)
        if shipping != self.partner_shipping_id and self.state != "cancel":
            self.partner_shipping_id = shipping
        return True

    def update_shopee_status(self, status):
        self.write({
            "shopee_order_status": status,
            "shopee_last_status_sync": fields.Datetime.now(),
        })
        self._shopee_cancel_if_cancelled()
