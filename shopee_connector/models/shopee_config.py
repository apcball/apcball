import logging
import secrets
import time
import urllib.parse
from datetime import timedelta, timezone

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .shopee_api import ShopeeAPI, ShopeeAPIError

_logger = logging.getLogger(__name__)

_MAX_PAGES = 40
# Shopee get_order_list accepts at most 15 days per request.
_ORDER_WINDOW = timedelta(days=15)


def _unix(dt):
    """Naive UTC datetime (Odoo) -> unix timestamp."""
    return int(dt.replace(tzinfo=timezone.utc).timestamp())


class ShopeeConfig(models.Model):
    _name = "shopee.config"
    _description = "Shopee Shop Connection"
    _check_company_auto = True
    _sql_constraints = [
        (
            "company_shop_unique",
            "unique(company_id, environment, shop_id)",
            "A Shopee shop can only be configured once per company and environment.",
        ),
    ]

    name = fields.Char(required=True, default="Shopee Shop")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    environment = fields.Selection(
        [("sandbox", "Sandbox"), ("production", "Production")],
        default="sandbox",
        required=True,
    )
    partner_id = fields.Char(string="Partner ID", required=True)
    partner_key = fields.Char(string="Partner Key", required=True, copy=False,
                              groups="sales_team.group_sale_manager")
    shop_id = fields.Char(string="Shop ID")

    customer_partner_id = fields.Many2one(
        "res.partner",
        string="Marketplace Customer",
        check_company=True,
        help="Fallback partner for orders whose buyer cannot be mapped. "
        "Normally each Shopee buyer is mapped to a shop-specific contact.",
    )
    shopee_price_vat_rate = fields.Float(
        string="Remove VAT % from Shopee Prices",
        default=7.0,
        help="Shopee prices include VAT. Order line Unit Price = Shopee price "
        "/ (1 + rate/100). Set 0 to keep Shopee prices as they are.",
    )
    shopee_shipping_product_id = fields.Many2one(
        "product.product", string="Shipping Product",
        check_company=True,
        help="Product for the shipping fee line (paid by the buyer). Empty = "
        "the product with Internal Reference Service04.",
    )
    shopee_voucher_product_id = fields.Many2one(
        "product.product", string="Seller Voucher Product",
        check_company=True,
        help="Product for the shop voucher discount line. A product whose "
        "Internal Reference equals the voucher code (e.g. MOGEN083) is used "
        "first. Empty = created automatically.",
    )
    shopee_voucher_prefix = fields.Char(
        string="Shop Voucher Code Prefix", default="MOGEN",
        help="Voucher codes starting with this text are the shop's own codes; "
        "other codes in the Seller Center export belong to Shopee.",
    )
    shopee_ship_cutoff_hour = fields.Float(
        string="Delivery Cut-off Time",
        default=14.0,
        help="Orders paid before this time ship the same day, later ones the "
        "next day (sets the order's Delivery Date).",
    )

    redirect_url = fields.Char(
        string="Redirect URL",
        help="Must match the Test/Live Redirect URL Domain configured on "
        "the Shopee Open Platform app.",
    )
    oauth_state = fields.Char(readonly=True, copy=False, groups="sales_team.group_sale_manager")
    oauth_state_expires_at = fields.Datetime(readonly=True, copy=False)
    webhook_secret = fields.Char(
        string="Webhook Secret", copy=False, groups="sales_team.group_sale_manager",
        help="Optional secret used to validate webhook signatures. If empty, "
        "the partner key is used.",
    )

    access_token = fields.Char(readonly=True, copy=False, groups="sales_team.group_sale_manager")
    refresh_token = fields.Char(readonly=True, copy=False, groups="sales_team.group_sale_manager")
    token_expires_at = fields.Datetime(readonly=True, copy=False)

    temp_auth_code = fields.Char(
        string="Authorization Code",
        copy=False, groups="sales_team.group_sale_manager",
        help="After authorizing the shop, paste either the 'code' value or "
        "the whole redirect URL (contains ?code=...&shop_id=...) here, then "
        "click 'Exchange Token'. Code expires after ~10 minutes.",
    )

    temp_access_token = fields.Char(
        string="Manual Access Token",
        groups="sales_team.group_sale_manager",
        copy=False,
        help="Optional: paste a token obtained elsewhere instead of using "
        "the OAuth flow.",
    )
    temp_refresh_token = fields.Char(
        string="Manual Refresh Token", copy=False, groups="sales_team.group_sale_manager"
    )
    temp_token_expires_at = fields.Datetime(
        string="Manual Token Expiry",
        copy=False,
        help="Leave empty to assume the token lasts 4 hours.",
    )

    # Stock push (Odoo -> Shopee)
    shopee_push_stock = fields.Boolean(
        string="Push Stock to Shopee",
        default=False,
        help="Master switch. When on, this shop's linked products push their "
        "Odoo free-to-use quantity back to Shopee (manual button or cron).",
    )
    shopee_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Stock Source Warehouse",
        check_company=True,
        help="Warehouse whose free-to-use quantity is published to Shopee. "
        "Defaults to the company's main warehouse.",
    )
    shopee_stock_location_id = fields.Many2one(
        "stock.location",
        string="Stock Source Location",
        check_company=True,
        domain="[('usage', '=', 'internal'), "
        "('warehouse_id', '=', shopee_warehouse_id)]",
        help="Optional internal location (and its sub-locations) whose "
        "free-to-use quantity is published to Shopee. Leave empty to use "
        "the whole warehouse.",
    )

    last_stock_sync = fields.Datetime(readonly=True)
    last_stock_sync_unmapped = fields.Integer(
        string="Unmapped Shopee Listings", readonly=True,
        help="Listings found by the last stock sync that are not linked to "
        "an Odoo product (no matching SKU and no manual mapping).",
    )
    last_order_sync = fields.Datetime(readonly=True)
    import_orders_from = fields.Datetime(
        string="Import Orders From",
        help="One-off backfill: when set, Import Orders Now fetches orders "
        "created since this date (existing orders are skipped), then clears "
        "this field.",
    )
    last_stock_push = fields.Datetime(readonly=True)
    last_order_status_sync = fields.Datetime(readonly=True)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id and (
            not self.shopee_warehouse_id
            or self.shopee_warehouse_id.company_id != self.company_id
        ):
            self.shopee_warehouse_id = self.env["stock.warehouse"].search(
                [("company_id", "=", self.company_id.id)], limit=1
            )

    @api.onchange("shopee_warehouse_id")
    def _onchange_shopee_warehouse_id(self):
        if (
            self.shopee_stock_location_id
            and self.shopee_stock_location_id.warehouse_id != self.shopee_warehouse_id
        ):
            self.shopee_stock_location_id = False

    @api.constrains("shopee_stock_location_id", "shopee_warehouse_id")
    def _check_shopee_stock_location(self):
        for config in self:
            location = config.shopee_stock_location_id
            if not location:
                continue
            if location.usage != "internal":
                raise ValidationError(
                    f"Stock Source Location '{location.display_name}' must be "
                    "an internal location."
                )
            if (
                config.shopee_warehouse_id
                and location.warehouse_id != config.shopee_warehouse_id
            ):
                raise ValidationError(
                    f"Stock Source Location '{location.display_name}' is not "
                    f"in warehouse '{config.shopee_warehouse_id.display_name}'."
                )

    # ------------------------------------------------------------------
    def _get_api(self):
        self.ensure_one()
        return ShopeeAPI(
            partner_id=self.partner_id,
            partner_key=self.partner_key,
            shop_id=self.shop_id,
            environment=self.environment,
            log_callback=self._write_api_log,
        )

    def _write_api_log(self, **values):
        # A rejected log insert must never leave the business transaction aborted.
        with self.env.cr.savepoint():
            self.env["shopee.api.log"].create_api_log(self, **values)

    def _ensure_valid_token(self):
        """Refresh access_token if it's missing or expired."""
        self.ensure_one()
        if not self.access_token or not self.token_expires_at:
            raise UserError(
                "No access token yet. Either run the authorization flow "
                "(Get Authorization Link -> authorize -> Exchange Token) or "
                "paste a token under 'Manual Tokens' and click "
                "'Save Manual Tokens'."
            )
        if fields.Datetime.now() >= self.token_expires_at:
            if not self.refresh_token:
                raise UserError(
                    "Access token expired and no refresh token is stored. "
                    "Re-authorize or paste a fresh token."
                )
            api = self._get_api()
            if not self.shop_id:
                raise UserError("Shop ID is required to refresh the access token.")
            data = api.refresh_access_token(self.refresh_token, int(self.shop_id))
            # Sandbox v2 returns token fields flat; classic API nests them
            resp = data.get("response") or data
            if not resp.get("access_token"):
                raise UserError(f"Failed to refresh Shopee token: {data}")
            self._store_tokens(resp)
        return self.access_token

    def _store_tokens(self, resp):
        self.write(
            {
                "access_token": resp["access_token"],
                "refresh_token": resp.get("refresh_token") or self.refresh_token,
                # Shopee access_token is valid 4h; refresh a bit early
                "token_expires_at": fields.Datetime.now()
                + timedelta(seconds=max(resp.get("expire_in", 14400) - 120, 60)),
            }
        )

    # ------------------------------------------------------------------
    # Actions - Authorization
    # ------------------------------------------------------------------
    def action_get_authorization_url(self):
        self.ensure_one()
        if not self.redirect_url:
            raise UserError("Set a Redirect URL first (must match the app's domain).")
        api = self._get_api()
        state = secrets.token_urlsafe(24)
        self.write({"oauth_state": state,
                    "oauth_state_expires_at": fields.Datetime.now() + timedelta(minutes=10)})
        url = api.get_authorization_url(self.redirect_url, state=state)
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def _accept_oauth_callback(self, state, code, shop_id):
        """Consume a pending authorization once, including concurrent callbacks."""
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM shopee_config WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["oauth_state", "oauth_state_expires_at", "shop_id", "active"])
        if (not self.active or not state or not code or not shop_id
                or not self.oauth_state or not state.isascii()
                or not secrets.compare_digest(self.oauth_state, state)
                or not self.oauth_state_expires_at
                or self.oauth_state_expires_at <= fields.Datetime.now()
                or (self.shop_id and self.shop_id != str(shop_id))):
            return False
        self.write({"temp_auth_code": code, "shop_id": str(shop_id),
                    "oauth_state": False, "oauth_state_expires_at": False})
        return True

    def action_exchange_token(self):
        self.ensure_one()
        raw = (self.temp_auth_code or "").strip()
        if not raw:
            raise UserError("Paste the authorization code first.")
        # Accept the full redirect URL (with ?code=...&shop_id=...) too
        code, shop_id = raw, self.shop_id
        if "code=" in raw:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
            if qs.get("code"):
                code = qs["code"][0].strip()
            if qs.get("shop_id"):
                shop_id = shop_id or qs["shop_id"][0].strip()
        if not shop_id:
            raise UserError("Shop ID is required (from the redirect query string).")
        api = self._get_api()
        try:
            data = api.get_access_token(code, int(shop_id))
        except ShopeeAPIError as exc:
            raise UserError(str(exc)) from exc
        # Sandbox v2 returns token fields flat; classic API nests them
        resp = data.get("response") or data
        if not resp.get("access_token"):
            raise UserError(f"Token exchange failed: {data}")
        self.write({"shop_id": str(shop_id), "oauth_state": False,
                    "oauth_state_expires_at": False})
        self._store_tokens(resp)
        self.temp_auth_code = False

    def action_save_manual_tokens(self):
        self.ensure_one()
        if not self.temp_access_token:
            raise UserError("Paste an Access Token first.")
        self.write(
            {
                "access_token": self.temp_access_token.strip(),
                "refresh_token": (self.temp_refresh_token or "").strip() or False,
                "token_expires_at": self.temp_token_expires_at
                or fields.Datetime.now() + timedelta(hours=4),
                "temp_access_token": False,
                "temp_refresh_token": False,
                "temp_token_expires_at": False,
            }
        )

    def action_test_connection(self):
        self.ensure_one()
        token = self._ensure_valid_token()
        api = self._get_api()
        try:
            data = api.get_shop_info(token)
        except ShopeeAPIError as exc:
            raise UserError(str(exc)) from exc
        resp = data.get("response") or {}
        shop_name = resp.get("shop_name") or data.get("shop_name")
        if not shop_name:
            raise UserError(f"Shopee connection failed: {data}")
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Connection OK",
                "message": f"Connected to Shopee shop: {shop_name}",
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _model_seller_stock(stock_info_v2):
        """Extract seller/available stock from a stock_info_v2 payload."""
        if not stock_info_v2:
            return 0
        summary = stock_info_v2.get("summary_info") or {}
        if "total_available_stock" in summary:
            return summary.get("total_available_stock") or 0
        total = 0
        for row in stock_info_v2.get("seller_stock") or []:
            total += row.get("stock") or 0
        return total

    @staticmethod
    def _model_location_id(stock_info_v2):
        """Return the first seller stock location_id (e.g. "SGZ"), if any."""
        for row in (stock_info_v2 or {}).get("seller_stock") or []:
            if row.get("location_id"):
                return row["location_id"]
        return False

    # ------------------------------------------------------------------
    # Actions - Sync (Shopee -> Odoo, reference only)
    # ------------------------------------------------------------------
    def action_sync_stock(self):
        self.ensure_one()
        self = self.with_company(self.company_id).with_context(allowed_company_ids=self.company_id.ids)
        token = self._ensure_valid_token()
        api = self._get_api()
        offset = 0
        updated = 0
        unmapped = 0
        Mapping = self.env["shopee.product.mapping"]
        for _page in range(_MAX_PAGES):
            item_resp = api.get_item_list(token, offset=offset)
            item_data = item_resp.get("response", {})
            items = item_data.get("item", [])
            if not items:
                break
            item_ids = [i["item_id"] for i in items]

            info_resp = api.get_item_base_info(token, item_ids)
            for item in info_resp.get("response", {}).get("item_list", []):
                item_id = item["item_id"]
                if item.get("has_model"):
                    models = api.get_model_list(token, item_id).get(
                        "response", {}
                    ).get("model", [])
                    for model in models:
                        sku = model.get("model_sku")
                        model_id = model.get("model_id")
                        if sku:
                            mapping = Mapping.search([
                                ("shopee_config_id", "=", self.id),
                                ("shopee_sku", "=", sku),
                                ("active", "=", True),
                            ], limit=1)
                            product = mapping.product_id or Mapping.find_product_by_sku(sku)
                        else:
                            # Shopee model has no variant SKU set - fall back to
                            # a mapping keyed by item_id/model_id (created
                            # manually, since there's no SKU to auto-match on).
                            mapping = Mapping.search([
                                ("shopee_config_id", "=", self.id),
                                ("shopee_item_id", "=", str(item_id)),
                                ("shopee_model_id", "=", str(model_id)),
                                ("active", "=", True),
                            ], limit=1)
                            product = mapping.product_id
                        stock_info = model.get("stock_info_v2")
                        stock_quantity = self._model_seller_stock(stock_info)
                        synced_at = fields.Datetime.now()
                        mapping = Mapping.upsert(
                            self, sku, product, item_id=item_id,
                            model_id=model_id, shopee_stock=stock_quantity,
                            stock_sync_at=synced_at,
                            item_name=item.get("item_name"),
                            model_name=model.get("model_name"),
                            location_id=self._model_location_id(stock_info),
                        )
                        # A mapping may already carry a product chosen by hand.
                        product = product or mapping.product_id
                        if not product:
                            unmapped += 1
                            _logger.warning(
                                "Shopee sync_stock (%s): item %s model %s "
                                "(sku=%r) is not linked to an Odoo product - "
                                "set a Shopee variation SKU or pick the "
                                "product in Product Mappings.",
                                self.name, item_id, model_id, sku,
                            )
                            continue
                        product.write({
                            "shopee_item_id": str(item_id),
                            "shopee_model_id": str(model_id),
                            "shopee_stock": stock_quantity,
                            "shopee_last_sync": synced_at,
                        })
                        updated += 1
                else:
                    sku = item.get("item_sku")
                    if sku:
                        mapping = Mapping.search([
                            ("shopee_config_id", "=", self.id),
                            ("shopee_sku", "=", sku),
                            ("active", "=", True),
                        ], limit=1)
                        product = mapping.product_id or Mapping.find_product_by_sku(sku)
                    else:
                        mapping = Mapping.search([
                            ("shopee_config_id", "=", self.id),
                            ("shopee_item_id", "=", str(item_id)),
                            ("shopee_model_id", "=", False),
                            ("active", "=", True),
                        ], limit=1)
                        product = mapping.product_id
                    stock_info = item.get("stock_info_v2")
                    stock_quantity = self._model_seller_stock(stock_info)
                    synced_at = fields.Datetime.now()
                    mapping = Mapping.upsert(
                        self, sku, product, item_id=item_id,
                        shopee_stock=stock_quantity, stock_sync_at=synced_at,
                        item_name=item.get("item_name"),
                        location_id=self._model_location_id(stock_info),
                    )
                    product = product or mapping.product_id
                    if not product:
                        unmapped += 1
                        _logger.warning(
                            "Shopee sync_stock (%s): item %s (sku=%r) is not "
                            "linked to an Odoo product.",
                            self.name, item_id, sku,
                        )
                        continue
                    product.write({
                        "shopee_item_id": str(item_id),
                        "shopee_model_id": False,
                        "shopee_stock": stock_quantity,
                        "shopee_last_sync": synced_at,
                    })
                    updated += 1

            if not item_data.get("has_next_page"):
                break
            offset = item_data.get("next_offset", offset + len(items))

        self.write({
            "last_stock_sync": fields.Datetime.now(),
            "last_stock_sync_unmapped": unmapped,
        })
        _logger.info("Shopee stock sync (%s): %s products updated, %s unmapped",
                     self.name, updated, unmapped)
        return updated

    def action_sync_stock_button(self):
        """Form button: run the stock pull and report what was not linked."""
        self.ensure_one()
        updated = self.action_sync_stock()
        message = f"{updated} product(s) updated from Shopee."
        if self.last_stock_sync_unmapped:
            message += (
                f" {self.last_stock_sync_unmapped} Shopee listing(s) are not "
                "linked to an Odoo product: add a variation SKU on Shopee "
                "matching the Odoo Internal Reference, or pick the product "
                "in Shopee > Product Mappings."
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Shopee stock sync",
                "message": message,
                "type": "warning" if self.last_stock_sync_unmapped else "success",
                "sticky": bool(self.last_stock_sync_unmapped),
            },
        }

    def action_sync_orders(self):
        """Import new Shopee orders.

        Normally from the last sync. When "Import Orders From" is set, from
        that date instead (one-off backfill, cleared afterwards). Shopee
        only accepts a limited time range per get_order_list call, so the
        period is fetched in windows.
        """
        self.ensure_one()
        token = self._ensure_valid_token()
        api = self._get_api()

        now = fields.Datetime.now()
        sync_from = self.import_orders_from or self.last_order_sync or (
            now - timedelta(days=2)
        )
        created = 0
        window_start = sync_from
        while window_start < now:
            window_end = min(window_start + _ORDER_WINDOW, now)
            created += self._sync_orders_window(
                api, token, _unix(window_start), _unix(window_end),
            )
            window_start = window_end

        self.write({"last_order_sync": now, "import_orders_from": False})
        _logger.info("Shopee order sync (%s): %s new orders created",
                     self.name, created)
        return created

    def _sync_orders_window(self, api, token, time_from, time_to):
        """Import the orders created between two unix timestamps."""
        SaleOrder = self.env["sale.order"]
        cursor = ""
        created = 0
        seen_cursors = set()
        for _page in range(_MAX_PAGES):
            list_resp = api.get_order_list(token, time_from, time_to, cursor)
            resp = list_resp.get("response", {})
            order_sns = [o["order_sn"] for o in resp.get("order_list", [])]
            if order_sns:
                detail_resp = api.get_order_detail(token, order_sns)
                details = detail_resp.get("response", {}).get("order_list", [])
                if {order["order_sn"] for order in details} != set(order_sns):
                    raise UserError("Shopee returned incomplete order details. Sync was not advanced.")
                for shopee_order in details:
                    existing = SaleOrder.search([
                        ("shopee_config_id", "=", self.id),
                        ("shopee_order_sn", "=", shopee_order["order_sn"]),
                    ], limit=1)
                    if existing:
                        continue
                    try:
                        with self.env.cr.savepoint():
                            order = SaleOrder.create_from_shopee(
                                shopee_order,
                                config=self,
                            )
                            order._shopee_fetch_escrow(api, token, shopee_order)
                        created += 1
                    except Exception as exc:
                        self.env["shopee.retry.queue"].enqueue(
                            self, "sync_order",
                            {"order_sn": shopee_order["order_sn"]},
                            str(exc),
                        )

            if not resp.get("more"):
                break
            cursor = resp.get("next_cursor", "")
            if not cursor or cursor in seen_cursors:
                raise UserError("Shopee returned an invalid order pagination cursor. Sync was not advanced.")
            seen_cursors.add(cursor)
        else:
            raise UserError("Shopee order pagination limit reached. Sync was not advanced; use a smaller date range.")
        return created

    def action_sync_orders_button(self):
        """Form button: import orders and report how many were created."""
        self.ensure_one()
        created = self.action_sync_orders()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Shopee orders",
                "message": f"{created} new order(s) imported from Shopee.",
                "type": "success",
                "sticky": False,
            },
        }

    def import_order_by_sn(self, order_sn):
        self.ensure_one()
        token = self._ensure_valid_token()
        order = self._get_api().get_order_detail(token, [order_sn]).get(
            "response", {}
        ).get("order_list", [])
        if len(order) != 1 or order[0].get("order_sn") != order_sn:
            raise UserError(f"Shopee order {order_sn} was not found.")
        SaleOrder = self.env["sale.order"]
        existing = SaleOrder.search([
            ("shopee_config_id", "=", self.id), ("shopee_order_sn", "=", order_sn)
        ], limit=1)
        if existing:
            existing.apply_shopee_detail(order[0])
            return existing
        return SaleOrder.create_from_shopee(order[0], config=self)

    def sync_order_statuses(self, order_sns=None):
        self.ensure_one()
        token = self._ensure_valid_token()
        SaleOrder = self.env["sale.order"]
        domain = [("is_shopee_order", "=", True), ("shopee_config_id", "=", self.id)]
        if order_sns is not None:
            domain.append(("shopee_order_sn", "in", order_sns))
        orders = SaleOrder.search(domain, order="id desc", limit=200 if order_sns is None else None)
        if order_sns is not None and set(order_sns) - set(orders.mapped("shopee_order_sn")):
            raise UserError("Import the missing Shopee order before syncing its status.")
        updated = 0
        api = self._get_api()
        for start in range(0, len(orders), 50):
            batch = orders[start:start + 50]
            details = api.get_order_status(
                token, batch.mapped("shopee_order_sn")
            ).get("response", {}).get("order_list", [])
            if {detail.get("order_sn") for detail in details} != set(batch.mapped("shopee_order_sn")):
                raise UserError("Shopee returned incomplete order statuses. Please retry.")
            for detail in details:
                order = batch.filtered(
                    lambda candidate: candidate.shopee_order_sn == detail.get("order_sn")
                )
                if order:
                    order.apply_shopee_detail(detail)
                    order._shopee_fetch_escrow(api, token, detail)
                    updated += 1
        self.last_order_status_sync = fields.Datetime.now()
        return updated

    def action_sync_order_status(self):
        self.ensure_one()
        updated = self.sync_order_statuses()
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": "Shopee order status",
                "message": f"{updated} order(s) updated.",
                "type": "success", "sticky": False,
            },
        }

    @staticmethod
    def _webhook_operation(payload):
        event = payload.get("event_type") or payload.get("code") or ""
        event_upper = str(event).upper()
        if "ORDER_STATUS" in event_upper:
            return "sync_order_status"
        if event_upper in {"ORDER_NEW", "ORDER_CREATE"}:
            return "sync_order"
        if "STOCK" in event_upper:
            return "sync_stock"
        return None

    def process_webhook(self, payload):
        self.ensure_one()
        data = payload.get("data") or payload
        order_sn = data.get("ordersn") or data.get("order_sn")
        operation = self._webhook_operation(payload)
        if operation == "sync_order_status" and order_sn:
            self.sync_order_statuses([order_sn])
            return "order_status_update"
        if operation == "sync_order" and order_sn:
            self.import_order_by_sn(order_sn)
            return "order_new"
        if operation == "sync_stock":
            self.action_sync_stock()
            return "item_stock_update"
        return "ignored"

    # ------------------------------------------------------------------
    # Actions - Push stock (Odoo -> Shopee)
    # ------------------------------------------------------------------
    def _shopee_stock_context(self):
        """Context giving product.free_qty for the stock published to Shopee."""
        self.ensure_one()
        if self.shopee_stock_location_id:
            # Odoo's 'location' context also counts child locations.
            return {"location": self.shopee_stock_location_id.id}
        warehouse = self.shopee_warehouse_id or self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not warehouse:
            raise UserError("No warehouse available for stock push.")
        return {"warehouse": warehouse.id}

    def _push_stock_for_products(self, products=None, force=False):
        """Push free-to-use qty to Shopee for the given (or all linked) products.

        ``force`` (Product Mapping button): push even when the product is not
        flagged for stock sync, the qty is unchanged or above the refill
        threshold. Returns the number of successful update_stock calls.
        """
        self.ensure_one()
        self = self.with_company(self.company_id).with_context(allowed_company_ids=self.company_id.ids)
        if products is not None:
            products = products.with_env(self.env)
            if any(product.company_id and product.company_id != self.company_id for product in products):
                raise UserError("Cannot push another company's stock to this shop.")
        if not self.shopee_push_stock:
            raise UserError(
                f"Shop '{self.name}': 'Push Stock to Shopee' is not enabled."
            )
        stock_context = self._shopee_stock_context()
        token = self._ensure_valid_token()
        api = self._get_api()

        Mapping = self.env["shopee.product.mapping"]
        if products is not None:
            targets = products
        else:
            mapped_products = Mapping.search([
                ("shopee_config_id", "=", self.id),
                ("active", "=", True),
                ("product_id.shopee_sync_stock_out", "=", True),
            ]).mapped("product_id")
            targets = self.env["product.product"].search([
                ("shopee_item_id", "!=", False),
                ("shopee_sync_stock_out", "=", True),
            ]) | mapped_products
        if products is not None and not force:
            targets = targets.filtered(
                lambda p: p.shopee_sync_stock_out
            )

        pushed = 0
        failures = []
        for product in targets.with_context(**stock_context):
            qty = int(max(product.free_qty, 0))
            mapping = Mapping.search([
                ("shopee_config_id", "=", self.id),
                ("product_id", "=", product.id),
                ("active", "=", True),
            ], limit=1)
            if mapping:
                qty = mapping._shopee_push_qty(qty)
            already_pushed = (
                mapping.last_pushed_stock if mapping else product.shopee_pushed_stock
            )
            pushed_at = mapping.last_stock_push if mapping else product.shopee_stock_push_date
            shopee_stock = mapping.shopee_stock if mapping else product.shopee_stock
            # Skip only when Shopee still shows what we last pushed; if the
            # stock changed on Shopee (orders, manual edits) push it back.
            if not force:
                if qty == already_pushed and qty == shopee_stock and pushed_at:
                    continue
                # Refill rule: only top Shopee up once it runs low.
                if mapping and mapping.refill_below and shopee_stock >= mapping.refill_below:
                    continue
            item_id = (
                (mapping.shopee_item_id if mapping else False)
                or product.shopee_item_id
            )
            model_id = (
                (mapping.shopee_model_id if mapping else False)
                or product.shopee_model_id
            )
            if not item_id:
                continue
            try:
                api.update_stock(
                    token,
                    int(item_id),
                    int(model_id) if model_id else 0,
                    qty,
                    location_id=mapping.shopee_location_id if mapping else False,
                )
            except ShopeeAPIError as exc:
                failures.append(f"{product.default_code or product.display_name}: {exc}")
                self.env["shopee.retry.queue"].enqueue(
                    self, "push_stock", {"product_id": product.id}, str(exc)
                )
                _logger.warning("Shopee stock push failed for %s: %s",
                                product.default_code, exc)
                continue
            product.write({
                "shopee_pushed_stock": qty,
                "shopee_stock": qty,
                "shopee_stock_push_date": fields.Datetime.now(),
            })
            if mapping:
                mapping.write({
                    "last_pushed_stock": qty,
                    "shopee_stock": qty,
                    "last_stock_push": fields.Datetime.now(),
                })
            pushed += 1

        self.last_stock_push = fields.Datetime.now()
        _logger.info("Shopee stock push (%s): %s ok, %s failed",
                     self.name, pushed, len(failures))
        if failures and products is not None:
            raise UserError(
                "Some stock pushes failed:\n" + "\n".join(failures[:20])
            )
        return pushed

    def action_push_stock(self):
        self.ensure_one()
        pushed = self._push_stock_for_products()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Shopee stock push",
                "message": f"{pushed} update(s) sent to Shopee.",
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Cron entry points (called by ir.cron, loop over all active configs)
    # ------------------------------------------------------------------
    @api.model
    def cron_sync_stock(self):
        for config in self.search([("active", "=", True)]):
            try:
                config.action_sync_stock()
            except Exception:
                _logger.exception("Shopee stock sync failed for %s", config.name)

    @api.model
    def cron_sync_orders(self):
        for config in self.search([("active", "=", True)]):
            try:
                config.action_sync_orders()
            except Exception:
                _logger.exception("Shopee order sync failed for %s", config.name)

    @api.model
    def cron_push_stock(self):
        for config in self.search(
            [("active", "=", True), ("shopee_push_stock", "=", True)]
        ):
            try:
                config._push_stock_for_products()
            except Exception:
                _logger.exception("Shopee stock push failed for %s", config.name)

    @api.model
    def cron_sync_order_status(self):
        for config in self.search([("active", "=", True)]):
            try:
                config.sync_order_statuses()
            except Exception:
                _logger.exception(
                    "Shopee order status sync failed for %s", config.name
                )

    @api.model
    def cron_process_retry_queue(self):
        self.env["shopee.retry.queue"].cron_process()

    @api.model
    def cron_refresh_tokens(self):
        for config in self.search(
            [("active", "=", True), ("access_token", "!=", False)]
        ):
            try:
                config._ensure_valid_token()
            except Exception:
                _logger.exception("Shopee token refresh failed for %s", config.name)
