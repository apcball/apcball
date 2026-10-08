import json
import logging
from datetime import datetime, time, timedelta
from html import escape

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

PAYMENT_SOURCES = [("order", "Lazada order data"), ("finance", "Lazada Finance API")]
CANCELLED = {"canceled", "cancelled"}
# Statuses after which Lazada can have posted the order's finance rows.
FINANCE_STATUSES = {"shipped", "delivered", "confirmed"}
# Finance rows that are buyer payments credited to the seller, not fees:
# 13 Item Price Credit, 8 Shipping Fee (Paid By Customer). 118 Promotional
# Charges Vouchers is the seller voucher, already shown as its own row.
_NOT_FEES = {"13", "8", "118"}


def _amount(value):
    """Lazada money values come as numbers or strings such as "1,234.50"."""
    try:
        return float(str(value).replace(",", "").strip() or 0)
    except (TypeError, ValueError):
        return 0.0


class SaleOrder(models.Model):
    _inherit = "sale.order"

    lazada_config_id = fields.Many2one(
        "lazada.config", string="Lazada Seller", copy=False, readonly=True,
        index=True, check_company=True,
    )
    lazada_order_id = fields.Char(
        string="Lazada Order ID", copy=False, index=True, readonly=True
    )
    lazada_order_status = fields.Char(readonly=True, copy=False)
    lazada_buyer_id = fields.Char(readonly=True, copy=False)
    lazada_last_status_sync = fields.Datetime(readonly=True, copy=False)
    lazada_payload = fields.Text(readonly=True, copy=False)
    is_lazada_order = fields.Boolean(default=False, copy=False)
    lazada_net_income = fields.Monetary(
        string="Lazada Order Income", readonly=True, copy=False,
        help="What Lazada pays the seller for this order after its fees.",
    )
    lazada_payment_source = fields.Selection(
        PAYMENT_SOURCES, readonly=True, copy=False,
    )

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
                    [("default_code", "=", str(sku))], limit=2
                )
                if len(product) > 1:
                    raise UserError(f"Lazada SKU {sku} matches multiple products. Set an explicit seller mapping.")
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
    def _lazada_summary_status(statuses):
        """One status for the order: the first active item's, or "canceled"."""
        statuses = [str(s).lower() for s in statuses or [] if s]
        active = [s for s in statuses if s not in CANCELLED]
        return active[0] if active else ("canceled" if statuses else "")

    @staticmethod
    def _lazada_active_items(items):
        """Items not cancelled; all items when the whole order is cancelled."""
        active = [i for i in items or [] if str(i.get("status") or "").lower() not in CANCELLED]
        return active or list(items or [])

    @api.model
    def _lazada_trade_channel_values(self):
        """{'trade_channel': 'lazada'} when marketplace_settlement offers it.

        The field and its choices live in another addon, so only set it if
        this database actually has it and offers the 'lazada' channel.
        """
        field = self._fields.get("trade_channel")
        if not field or field.type != "selection":
            return {}
        if "lazada" not in field.get_values(self.env):
            return {}
        return {"trade_channel": "lazada"}

    @api.model
    def _lazada_backfill_trade_channel(self):
        """Set Trade Channel = Lazada on imported orders that have none."""
        values = self._lazada_trade_channel_values()
        if not values:
            return 0
        orders = self.with_context(active_test=False).search([
            ("is_lazada_order", "=", True),
            ("trade_channel", "=", False),
        ])
        orders.write(values)
        return len(orders)

    @staticmethod
    def _lazada_address_note(order):
        buyer = escape(" ".join(filter(None, [
            str(order.get("customer_first_name") or ""), str(order.get("customer_last_name") or ""),
        ])).strip())
        return f"<p>Lazada buyer: {buyer}</p>" if buyer and "**" not in buyer else ""

    @api.model
    def create_from_lazada(self, order_id, partner=None, config=None):
        if not config:
            raise ValueError("A lazada.config is required to import orders.")
        self = self.with_company(config.company_id).with_context(
            allowed_company_ids=[config.company_id.id],
        )
        token = config._ensure_valid_token()
        api = config._get_api()
        order = api.get_order(token, str(order_id)) or {}
        if not order or str(order.get("order_id") or "") != str(order_id):
            raise UserError(f"Lazada order {order_id} was not found.")
        items = api.get_order_items(token, str(order_id)) or []

        Partner = self.env["res.partner"]
        buyer_name = " ".join(filter(None, [
            order.get("customer_first_name"), order.get("customer_last_name"),
        ])) or "Lazada Buyer"
        shipping_partner = None
        if partner is None:
            partner = Partner.find_or_create_lazada_buyer(config, order)
            if partner:
                shipping_partner = self._lazada_apply_tax_identity(partner, order, config)
            elif config.customer_partner_id:
                partner = config.customer_partner_id
        if partner is None:
            partner = Partner.search([("name", "=", buyer_name)], limit=1)
            if not partner:
                partner = Partner.with_context(skip_partner_required_fields=True).create(
                    {"name": buyer_name, "customer_rank": 1}
                )

        # Lazada sends one item per unit: one Odoo line per product and price.
        lines = {}
        for item in self._lazada_active_items(items):
            product = self._lazada_find_product(item, config=config)
            # A free/promotional item has a legitimate price of zero.
            price = next((item[key] for key in ("item_price", "paid_price")
                          if item.get(key) not in (None, "")), 0)
            price = self._lazada_price_ex_vat(_amount(price), config)
            name = item.get("name") or product.name
            line = lines.setdefault((product.id, name, round(price, 6)), {
                "product_id": product.id, "name": name,
                "product_uom_qty": 0, "price_unit": price,
            })
            line["product_uom_qty"] += _amount(item.get("quantity")) or 1

        status = self._lazada_summary_status(order.get("statuses"))
        values = {
            "company_id": config.company_id.id,
            "partner_id": partner.id,
            "lazada_config_id": config.id,
            "lazada_order_id": str(order_id),
            "lazada_order_status": status,
            "lazada_buyer_id": partner.lazada_buyer_id or buyer_name,
            "lazada_payload": json.dumps(
                {"order": order, "items": items},
                ensure_ascii=False, default=str,
            ),
            "is_lazada_order": True,
            "order_line": [fields.Command.create(vals) for vals in lines.values()],
            "origin": f"Lazada {order_id}",
            "client_order_ref": str(order.get("order_number") or order_id),
            "note": self._lazada_address_note(order) or False,
        }
        if shipping_partner and shipping_partner != partner:
            values["partner_shipping_id"] = shipping_partner.id
        values.update(self._lazada_trade_channel_values())
        if status != "unpaid":
            commitment = self._lazada_commitment_date(
                self._lazada_parse_datetime(order.get("created_at")), config,
            )
            if commitment:
                values["commitment_date"] = commitment
        sale = self.create(values)
        sale._lazada_apply_payment(sale._lazada_payment_from_order(order, items))
        sale._lazada_cancel_if_cancelled()
        return sale

    @api.model
    def _lazada_apply_tax_identity(self, partner, order, config):
        """Tax invoice data on the buyer; returns the delivery contact.

        Best effort: invalid tax data must not block the order import.
        """
        try:
            with self.env.cr.savepoint():
                applied = partner._lazada_apply_tax_invoice(order, config)
                if applied or partner.vat:
                    return partner._lazada_update_from_order(order, config)
        except Exception as exc:  # noqa: BLE001 - optional data
            _logger.warning("Lazada tax invoice data rejected for order %s: %s",
                            order.get("order_id"), exc)
        return partner

    @api.model
    def _lazada_price_ex_vat(self, price, config=None):
        """Lazada prices include VAT; remove the configured rate (7%)."""
        rate = config.lazada_price_vat_rate if config else 0.0
        if not price or not rate:
            return price
        return price / (1 + rate / 100.0)

    @api.model
    def _lazada_local_tz(self):
        return pytz.timezone(self.env.user.tz or "Asia/Bangkok")

    @staticmethod
    def _lazada_parse_datetime(value):
        """Lazada dates ("2024-01-15 10:20:30 +0700" or ISO 8601) -> aware datetime."""
        if not value:
            return None
        text = str(value).strip()
        for fmt in ("%Y-%m-%d %H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else None

    @api.model
    def _lazada_commitment_date(self, paid_at, config=None):
        """Delivery Date from the payment time and the seller's cut-off.

        ``paid_at``: a timezone-aware datetime or a unix timestamp. Paid
        before the cut-off (default 14:00) ships that day, otherwise the next
        day. Returns a naive UTC datetime at the cut-off time.
        """
        if not paid_at or not config:
            return False
        tz = self._lazada_local_tz()
        if isinstance(paid_at, datetime):
            local = paid_at.astimezone(tz)
        else:
            local = datetime.fromtimestamp(int(paid_at), tz)
        cutoff = config.lazada_ship_cutoff_hour or 14.0
        hours, minutes = int(cutoff), int(round((cutoff % 1) * 60))
        ship_day = local.date()
        if (local.hour, local.minute) >= (hours, minutes):
            ship_day += timedelta(days=1)
        ship_at = tz.localize(datetime.combine(ship_day, time(hours, minutes)))
        return ship_at.astimezone(pytz.utc).replace(tzinfo=None)

    def _lazada_set_commitment_date(self, paid_at):
        """Fill Delivery Date once the order is paid."""
        for order in self.filtered(lambda o: not o.commitment_date and o.state != "cancel"):
            commitment = order._lazada_commitment_date(paid_at, order.lazada_config_id)
            if commitment:
                order.commitment_date = commitment

    # ------------------------------------------------------------------
    # Payment details (shipping, seller voucher, Lazada fees)
    # ------------------------------------------------------------------
    def _lazada_service_product(self, config, field_name, code, name):
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

    def _lazada_payment_lines(self, payment):
        config = self.lazada_config_id
        lines = []
        if payment.get("shipping"):
            product = self._lazada_service_product(
                config, "lazada_shipping_product_id", "Service04", "ค่าขนส่ง",
            )
            lines.append({
                "lazada_line_type": "shipping",
                "product_id": product.id,
                "name": product.display_name,
                "product_uom_qty": 1,
                "price_unit": self._lazada_price_ex_vat(payment["shipping"], config),
                "sequence": 9000,
            })
        if payment.get("voucher_amount"):
            codes = payment.get("voucher_codes") or []
            Product = self.env["product.product"]
            product = Product.search(
                [("default_code", "in", codes)], limit=1,
            ) if codes else Product
            if not product:
                product = self._lazada_service_product(
                    config, "lazada_voucher_product_id", False,
                    "Lazada Seller Voucher",
                )
            label = "โค้ดส่วนลดร้านค้าจากผู้ขาย"
            if codes:
                label += " - " + ", ".join(codes)
            lines.append({
                "lazada_line_type": "voucher",
                "product_id": product.id,
                "name": label,
                "product_uom_qty": 1,
                "price_unit": -self._lazada_price_ex_vat(
                    payment["voucher_amount"], config,
                ),
                "sequence": 9001,
            })
        return lines

    def _lazada_payment_note(self, payment):
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
        fees = [(label, value) for label, value in payment.get("fees") or [] if value]
        fee_total = sum(value for _label, value in fees)
        if fee_total:
            rows.append(("ค่าธรรมเนียม", -fee_total))
            rows += [(f"&nbsp;&nbsp;{escape(label)}", -value) for label, value in fees]
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
        payload = json.loads(self.lazada_payload or "{}")
        buyer = self._lazada_address_note(payload.get("order") or {})
        source = dict(PAYMENT_SOURCES).get(payment.get("source"), "")
        return (
            f"{buyer}<p><b>Lazada payment details</b> ({escape(source)})</p>"
            f"<table>{body}</table>"
        )

    def _lazada_apply_payment(self, payment):
        """Add shipping / seller voucher lines and the fee summary.

        Only quotations are changed; lines added earlier are replaced so the
        data can be re-applied (order data first, Finance API later).
        """
        self.ensure_one()
        if not payment or self.state not in ("draft", "sent"):
            return False
        commands = [
            fields.Command.delete(line.id)
            for line in self.order_line.filtered("lazada_line_type")
        ]
        commands += [
            fields.Command.create(vals) for vals in self._lazada_payment_lines(payment)
        ]
        self.write({
            "order_line": commands,
            "note": self._lazada_payment_note(payment),
            "lazada_net_income": payment.get("net_income") or 0.0,
            "lazada_payment_source": payment.get("source"),
        })
        return True

    def _lazada_payment_from_order(self, order, items):
        """Shipping and seller voucher as known when the order is placed."""
        config = self.lazada_config_id
        active = self._lazada_active_items(items)
        products_total = sum(
            _amount(i.get("item_price")) * (_amount(i.get("quantity")) or 1) for i in active
        )
        voucher = _amount(order.get("voucher_seller")) or sum(
            _amount(i.get("voucher_seller")) for i in active
        )
        codes = []
        for item in active:
            for code in str(item.get("voucher_code_seller") or "").split(","):
                if code.strip() and code.strip() not in codes:
                    codes.append(code.strip())
        if not codes:
            prefix = (config.lazada_voucher_prefix or "").strip().upper() if config else ""
            for code in str(order.get("voucher_code") or "").split(","):
                code = code.strip()
                if code and (not prefix or code.upper().startswith(prefix)) and code not in codes:
                    codes.append(code)
        return {
            "source": "order",
            "products_total": products_total,
            "shipping": _amount(order.get("shipping_fee")),
            "voucher_amount": voucher,
            "voucher_codes": codes if voucher else [],
            "fees": [],
            "net_income": None,
        }

    @api.model
    def _lazada_payment_from_finance(self, rows, base):
        """Fees and net income from Finance API rows of one order."""
        if not rows:
            return False
        fees = {}
        net = 0.0
        for row in rows:
            amount = _amount(row.get("amount"))
            net += amount
            if str(row.get("fee_type") or "") in _NOT_FEES or amount >= 0:
                continue
            label = str(row.get("fee_name") or row.get("transaction_type") or "Other")
            fees[label] = fees.get(label, 0.0) - amount
        return dict(base, source="finance", fees=sorted(fees.items()),
                    net_income=round(net, 2))

    def _lazada_fetch_finance(self, api, token):
        """Best effort: Lazada posts finance rows only after settlement."""
        for order in self:
            if (
                order.lazada_payment_source == "finance"
                or order.state not in ("draft", "sent")
                or order.lazada_order_status not in FINANCE_STATUSES
            ):
                continue
            payload = json.loads(order.lazada_payload or "{}")
            start = (order.date_order or fields.Datetime.now()) - timedelta(days=1)
            try:
                rows = api.get_finance_transactions(
                    token, order.lazada_order_id, start.date(),
                    fields.Date.context_today(order),
                )
            except Exception as exc:  # noqa: BLE001 - optional data
                _logger.warning("Lazada finance %s: %s", order.lazada_order_id, exc)
                continue
            payment = order._lazada_payment_from_finance(
                rows, order._lazada_payment_from_order(
                    payload.get("order") or {}, payload.get("items") or [],
                ),
            )
            if payment:
                order._lazada_apply_payment(payment)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------
    def _lazada_cancel_if_cancelled(self):
        """React to a Lazada order that became cancelled.

        Draft/sent quotations are cancelled outright. A confirmed sales order
        may already have deliveries or invoices, so it is left alone and only
        tagged for staff to review manually.
        """
        cancelled = self.filtered(lambda order: order.lazada_order_status in CANCELLED)
        to_cancel = cancelled.filtered(lambda order: order.state in ("draft", "sent"))
        if to_cancel:
            to_cancel._action_cancel()
        confirmed_cancelled = (cancelled - to_cancel).filtered(lambda order: order.state != "cancel")
        if confirmed_cancelled:
            confirmed_cancelled.write({
                "tag_ids": [fields.Command.link(
                    self.env.ref("lazada_connector.tag_lazada_cancelled_after_confirm").id
                )],
            })
        return to_cancel

    def apply_lazada_detail(self, order_data):
        """Refresh status, buyer contact and Delivery Date from /order/get.

        Lazada may mask the recipient until the order is paid, so the address
        is often only available on a later sync.
        """
        status = self._lazada_summary_status(order_data.get("statuses"))
        for order in self:
            order._lazada_apply_recipient(order_data)
            if status and status != "unpaid":
                paid_at = (self._lazada_parse_datetime(order_data.get("updated_at"))
                           if order.lazada_order_status == "unpaid" else None) \
                    or self._lazada_parse_datetime(order_data.get("created_at"))
                order._lazada_set_commitment_date(paid_at)
        if status:
            self.update_lazada_status(status)

    def _lazada_apply_recipient(self, order_data):
        """Update the buyer / delivery address from the order's recipient."""
        self.ensure_one()
        partner = self.partner_id
        if not partner.lazada_config_id or partner.lazada_config_id != self.lazada_config_id:
            return False
        shipping = partner._lazada_update_from_order(order_data, self.lazada_config_id)
        if shipping != self.partner_shipping_id and self.state != "cancel":
            self.partner_shipping_id = shipping
        return True

    def refresh_lazada_status(self, api=None, token=None):
        self.ensure_one()
        config = self.lazada_config_id
        if not config:
            return self
        if api is None:
            token = config._ensure_valid_token()
            api = config._get_api()
        order = api.get_order(token, self.lazada_order_id) or {}
        if order:
            self.apply_lazada_detail(order)
            self._lazada_fetch_finance(api, token)
        return self

    def update_lazada_status(self, status):
        self.write({
            "lazada_order_status": status,
            "lazada_last_status_sync": fields.Datetime.now(),
        })
        self._lazada_cancel_if_cancelled()
