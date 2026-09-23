import json
import logging
import secrets
import time
import urllib.parse
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .lazada_api import LazadaAPI, LazadaAPIError

_logger = logging.getLogger(__name__)

_MAX_PAGES = 40


class LazadaConfig(models.Model):
    _name = "lazada.config"
    _description = "Lazada Seller Connection"
    _check_company_auto = True
    _sql_constraints = [
        (
            "company_seller_unique",
            "unique(company_id, environment, seller_id)",
            "A Lazada seller can only be configured once per company and "
            "environment.",
        ),
    ]

    name = fields.Char(required=True, default="Lazada Seller")
    active = fields.Boolean(default=True)
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    environment = fields.Selection(
        [("sandbox", "Sandbox"), ("production", "Production")],
        default="production",
        required=True,
        help=(
            "Retained for configuration compatibility. Lazada uses the same "
            "regional API hosts and central OAuth host for both values."
        ),
    )
    region = fields.Selection(
        [
            ("th", "Thailand (lazada.co.th)"),
            ("sg", "Singapore (lazada.sg)"),
            ("my", "Malaysia (lazada.com.my)"),
            ("id", "Indonesia (lazada.co.id)"),
            ("ph", "Philippines (lazada.com.ph)"),
            ("vn", "Vietnam (lazada.vn)"),
            ("cb", "Cross-border (lazada.com)"),
        ],
        default="th",
        required=True,
        help="API host region - must match the seller's Lazada site.",
    )
    app_key = fields.Char(string="App Key", required=True)
    app_secret = fields.Char(string="App Secret", required=True)
    seller_id = fields.Char(string="Seller ID")

    customer_partner_id = fields.Many2one(
        "res.partner",
        string="Marketplace Customer",
        check_company=True,
        help="Fallback partner for orders whose buyer cannot be mapped. "
        "Normally each Lazada buyer is mapped to a seller-specific contact.",
    )

    redirect_url = fields.Char(
        string="Redirect URL",
        help="Must match the callback URL configured on the Lazada "
        "Open Platform app.",
    )
    oauth_state = fields.Char(readonly=True, copy=False)
    webhook_secret = fields.Char(
        string="Webhook Secret", copy=False,
        help="Optional secret used to validate webhook signatures. If empty, "
        "the app secret is used.",
    )

    access_token = fields.Char(readonly=True, copy=False)
    refresh_token = fields.Char(readonly=True, copy=False)
    token_expires_at = fields.Datetime(readonly=True, copy=False)

    temp_auth_code = fields.Char(
        string="Authorization Code",
        help="After authorizing the seller, paste either the 'code' value or "
        "the whole redirect URL (contains ?code=...) here, then click "
        "'Exchange Token'.",
    )

    temp_access_token = fields.Char(
        string="Manual Access Token",
        copy=False,
        help="Optional: paste a token obtained elsewhere instead of using "
        "the OAuth flow.",
    )
    temp_refresh_token = fields.Char(
        string="Manual Refresh Token", copy=False
    )
    temp_token_expires_at = fields.Datetime(
        string="Manual Token Expiry",
        copy=False,
        help="Leave empty to assume the token lasts 7 days.",
    )

    # Stock push (Odoo -> Lazada)
    lazada_push_stock = fields.Boolean(
        string="Push Stock to Lazada",
        default=False,
        help="Master switch. When on, this seller's linked products push "
        "their Odoo free-to-use quantity back to Lazada (manual button or "
        "cron).",
    )
    lazada_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Stock Source Warehouse",
        check_company=True,
        help="Warehouse whose free-to-use quantity is published to Lazada. "
        "Defaults to the company's main warehouse.",
    )

    last_stock_sync = fields.Datetime(readonly=True)
    last_order_sync = fields.Datetime(readonly=True)
    last_stock_push = fields.Datetime(readonly=True)
    last_order_status_sync = fields.Datetime(readonly=True)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id and (
            not self.lazada_warehouse_id
            or self.lazada_warehouse_id.company_id != self.company_id
        ):
            self.lazada_warehouse_id = self.env["stock.warehouse"].search(
                [("company_id", "=", self.company_id.id)], limit=1
            )

    # ------------------------------------------------------------------
    def _get_api(self):
        self.ensure_one()
        return LazadaAPI(
            app_key=self.app_key,
            app_secret=self.app_secret,
            region=self.region,
            environment=self.environment,
            log_callback=self._write_api_log,
        )

    def _write_api_log(self, **values):
        self.env["lazada.api.log"].create_api_log(self, **values)

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
            try:
                data = api.refresh_access_token(self.refresh_token)
            except LazadaAPIError as exc:
                raise UserError(str(exc)) from exc
            if not data.get("access_token"):
                raise UserError(f"Failed to refresh Lazada token: {data}")
            self._store_tokens(data)
        return self.access_token

    def _store_tokens(self, resp):
        self.write(
            {
                "access_token": resp["access_token"],
                "refresh_token": resp.get("refresh_token") or self.refresh_token,
                # Lazada access_token is valid ~7d; refresh a bit early
                "token_expires_at": fields.Datetime.now()
                + timedelta(seconds=max(resp.get("expires_in", 604800) - 120, 60)),
            }
        )

    # ------------------------------------------------------------------
    # Actions - Authorization
    # ------------------------------------------------------------------
    def action_get_authorization_url(self):
        self.ensure_one()
        if not self.redirect_url:
            raise UserError("Set a Redirect URL first (must match the app's callback domain).")
        api = self._get_api()
        state = secrets.token_urlsafe(24)
        # A Lazada authorization code is single-use. Discard a code left by
        # an interrupted legacy/manual flow before starting a fresh one.
        self.write({"oauth_state": state, "temp_auth_code": False})
        url = api.get_authorization_url(self.redirect_url, state=state)
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def action_exchange_token(self):
        self.ensure_one()
        raw = (self.temp_auth_code or "").strip()
        if not raw:
            raise UserError("Paste the authorization code first.")
        # Accept the full redirect URL (with ?code=...) too
        code = raw
        if "code=" in raw:
            qs = urllib.parse.parse_qs(urllib.parse.urlparse(raw).query)
            if qs.get("code"):
                code = qs["code"][0].strip()
        try:
            self._complete_authorization(code)
        except LazadaAPIError as exc:
            raise UserError(str(exc)) from exc

    def _complete_authorization(self, code):
        """Exchange one callback code and always invalidate the OAuth attempt."""
        self.ensure_one()
        try:
            data = self._get_api().get_access_token(code)
            if not data.get("access_token"):
                raise UserError("Lazada did not return an access token.")
            self._store_tokens(data)
        finally:
            # Codes can only be used once. Keeping one after any outcome lets
            # a later click fail misleadingly with Lazada's InvalidCode.
            self.write({"oauth_state": False, "temp_auth_code": False})

        # Best effort: Lazada does not return the seller id on the token
        # exchange, so fill it from /seller/get for webhook routing.
        seller_info = (data.get("country_user_info") or [{}])[0]
        if seller_info.get("seller_id") and not self.seller_id:
            self.seller_id = str(seller_info["seller_id"])
        try:
            seller = self._get_api().get_seller_info(self.access_token) or {}
            if seller.get("seller_id") and not self.seller_id:
                self.seller_id = str(seller["seller_id"])
        except Exception:
            _logger.info(
                "Lazada seller lookup after token exchange failed; "
                "Test Connection will fill the seller id.", exc_info=True
            )

    def action_save_manual_tokens(self):
        self.ensure_one()
        if not self.temp_access_token:
            raise UserError("Paste an Access Token first.")
        self.write(
            {
                "access_token": self.temp_access_token.strip(),
                "refresh_token": (self.temp_refresh_token or "").strip() or False,
                "token_expires_at": self.temp_token_expires_at
                or fields.Datetime.now() + timedelta(days=7),
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
            data = api.get_seller_info(token) or {}
        except LazadaAPIError as exc:
            raise UserError(str(exc)) from exc
        seller_name = (
            data.get("seller_name")
            or data.get("name")
            or data.get("login")
        )
        if not seller_name:
            raise UserError(f"Lazada connection failed: {data}")
        if data.get("seller_id") and not self.seller_id:
            self.seller_id = str(data["seller_id"])
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Connection OK",
                "message": f"Connected to Lazada seller: {seller_name}",
                "type": "success",
                "sticky": False,
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_int(value):
        try:
            return int(float(value or 0))
        except (TypeError, ValueError):
            return 0

    # ------------------------------------------------------------------
    # Actions - Sync (Lazada -> Odoo, reference only)
    # ------------------------------------------------------------------
    def action_sync_stock(self):
        self.ensure_one()
        token = self._ensure_valid_token()
        api = self._get_api()
        Product = self.env["product.product"]
        Mapping = self.env["lazada.product.mapping"]

        offset = 0
        updated = 0
        for _page in range(_MAX_PAGES):
            data = api.get_products(token, offset=offset) or {}
            products = data.get("products") or []
            if not products:
                break
            for product in products:
                item_id = product.get("item_id")
                for sku in product.get("skus") or []:
                    seller_sku = sku.get("SellerSku") or sku.get("seller_sku")
                    if not seller_sku:
                        continue
                    mapping = Mapping.search([
                        ("lazada_config_id", "=", self.id),
                        ("seller_sku", "=", seller_sku),
                        ("active", "=", True),
                    ], limit=1)
                    record = mapping.product_id or Product.search(
                        [("default_code", "=", seller_sku)], limit=1
                    )
                    if not record:
                        continue
                    sku_id = sku.get("SkuId") or sku.get("sku_id")
                    record.write({
                        "lazada_item_id": str(item_id) if item_id else False,
                        "lazada_sku_id": str(sku_id) if sku_id else False,
                        "lazada_stock": self._parse_int(sku.get("quantity")),
                        "lazada_last_sync": fields.Datetime.now(),
                    })
                    Mapping.upsert(
                        self, seller_sku, record,
                        item_id=item_id, sku_id=sku_id,
                    )
                    updated += 1
            if len(products) < 50:
                break
            offset += len(products)

        self.last_stock_sync = fields.Datetime.now()
        _logger.info("Lazada stock sync (%s): %s products updated",
                     self.name, updated)
        return updated

    def action_sync_orders(self):
        self.ensure_one()
        token = self._ensure_valid_token()
        api = self._get_api()
        SaleOrder = self.env["sale.order"]

        created_to = int(time.time())
        sync_from = self.last_order_sync or (
            fields.Datetime.now() - timedelta(days=2)
        )
        created_after = int(sync_from.timestamp())

        offset = 0
        created = 0
        for _page in range(_MAX_PAGES):
            data = api.get_orders(
                token, created_after, created_before=created_to, offset=offset
            ) or {}
            orders = data.get("orders") or []
            if not orders:
                break
            for entry in orders:
                order_id = str(entry.get("order_id") or "")
                if not order_id:
                    continue
                existing = SaleOrder.search([
                    ("lazada_config_id", "=", self.id),
                    ("lazada_order_id", "=", order_id),
                ], limit=1)
                if existing:
                    continue
                try:
                    SaleOrder.create_from_lazada(order_id, config=self)
                    created += 1
                except Exception as exc:
                    self.env["lazada.retry.queue"].enqueue(
                        self, "sync_order",
                        {"order_id": order_id},
                        str(exc),
                    )
            offset += len(orders)

        self.last_order_sync = fields.Datetime.now()
        _logger.info("Lazada order sync (%s): %s new orders created",
                     self.name, created)
        return created

    def import_order_by_id(self, order_id):
        self.ensure_one()
        SaleOrder = self.env["sale.order"]
        existing = SaleOrder.search([
            ("lazada_config_id", "=", self.id),
            ("lazada_order_id", "=", str(order_id)),
        ], limit=1)
        if existing:
            existing.refresh_lazada_status()
            return existing
        return SaleOrder.create_from_lazada(str(order_id), config=self)

    def sync_order_statuses(self, order_ids=None):
        self.ensure_one()
        token = self._ensure_valid_token()
        SaleOrder = self.env["sale.order"]
        domain = [("is_lazada_order", "=", True),
                  ("lazada_config_id", "=", self.id)]
        orders = SaleOrder.search(domain, order="id desc", limit=200)
        if order_ids:
            orders = orders.filtered(
                lambda order: order.lazada_order_id in order_ids
            )
        updated = 0
        api = self._get_api()
        for order in orders:
            try:
                order.refresh_lazada_status(api=api, token=token)
                updated += 1
            except Exception as exc:
                self.env["lazada.retry.queue"].enqueue(
                    self, "sync_order_status",
                    {"order_id": order.lazada_order_id},
                    str(exc),
                )
        self.last_order_status_sync = fields.Datetime.now()
        return updated

    def action_sync_order_status(self):
        self.ensure_one()
        updated = self.sync_order_statuses()
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {
                "title": "Lazada order status",
                "message": f"{updated} order(s) updated.",
                "type": "success", "sticky": False,
            },
        }

    def process_webhook(self, payload):
        self.ensure_one()
        data = payload.get("data") or payload
        # Lazada pushes often wrap the real payload in a JSON string under
        # the "message" key.
        message = data.get("message")
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except ValueError:
                message = {}
        if isinstance(message, dict):
            data = message
        event = str(
            payload.get("event_type") or payload.get("type")
            or data.get("type") or ""
        ).upper()
        order_id = (
            data.get("order_id") or data.get("OrderId")
            or data.get("trade_order_id")
        )
        if order_id and ("STATUS" in event or "ORDER" in event):
            order_id = str(order_id)
            SaleOrder = self.env["sale.order"]
            existing = SaleOrder.search([
                ("lazada_config_id", "=", self.id),
                ("lazada_order_id", "=", order_id),
            ], limit=1)
            if existing:
                self.sync_order_statuses([order_id])
                return "order_status_update"
            self.import_order_by_id(order_id)
            return "order_new"
        if "STOCK" in event or "SKU" in event:
            self.action_sync_stock()
            return "sku_stock_update"
        return "ignored"

    # ------------------------------------------------------------------
    # Actions - Push stock (Odoo -> Lazada)
    # ------------------------------------------------------------------
    def _push_stock_for_products(self, products=None):
        """Push free-to-use qty to Lazada for the given (or all linked) products.

        Returns the number of successful update calls.
        """
        self.ensure_one()
        if not self.lazada_push_stock:
            raise UserError(
                f"Seller '{self.name}': 'Push Stock to Lazada' is not enabled."
            )
        token = self._ensure_valid_token()
        api = self._get_api()
        warehouse = self.lazada_warehouse_id or self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not warehouse:
            raise UserError("No warehouse available for stock push.")

        Mapping = self.env["lazada.product.mapping"]
        if products is not None:
            targets = products.filtered(lambda p: p.lazada_sync_stock_out)
        else:
            mapped_products = Mapping.search([
                ("lazada_config_id", "=", self.id),
                ("active", "=", True),
                ("product_id.lazada_sync_stock_out", "=", True),
            ]).mapped("product_id")
            targets = self.env["product.product"].search([
                ("lazada_item_id", "!=", False),
                ("lazada_sync_stock_out", "=", True),
            ]) | mapped_products

        pushed = 0
        failures = []
        for product in targets.with_context(warehouse=warehouse.id):
            qty = int(max(product.free_qty, 0))
            mapping = Mapping.search([
                ("lazada_config_id", "=", self.id),
                ("product_id", "=", product.id),
                ("active", "=", True),
            ], limit=1)
            already_pushed = (
                mapping.last_pushed_stock if mapping else product.lazada_pushed_stock
            )
            pushed_at = mapping.last_stock_push if mapping else product.lazada_stock_push_date
            if qty == already_pushed and pushed_at:
                continue
            item_id = (
                (mapping.lazada_item_id if mapping else False)
                or product.lazada_item_id
            )
            sku_id = (
                (mapping.lazada_sku_id if mapping else False)
                or product.lazada_sku_id
            )
            seller_sku = product.default_code
            if not item_id or not seller_sku:
                continue
            try:
                api.update_stock(token, seller_sku, sku_id, qty)
            except LazadaAPIError as exc:
                failures.append(f"{seller_sku}: {exc}")
                self.env["lazada.retry.queue"].enqueue(
                    self, "push_stock", {"product_id": product.id}, str(exc)
                )
                _logger.warning("Lazada stock push failed for %s: %s",
                                seller_sku, exc)
                continue
            product.write({
                "lazada_pushed_stock": qty,
                "lazada_stock_push_date": fields.Datetime.now(),
            })
            if mapping:
                mapping.write({
                    "last_pushed_stock": qty,
                    "last_stock_push": fields.Datetime.now(),
                })
            pushed += 1

        self.last_stock_push = fields.Datetime.now()
        _logger.info("Lazada stock push (%s): %s ok, %s failed",
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
                "title": "Lazada stock push",
                "message": f"{pushed} update(s) sent to Lazada.",
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
                _logger.exception("Lazada stock sync failed for %s", config.name)

    @api.model
    def cron_sync_orders(self):
        for config in self.search([("active", "=", True)]):
            try:
                config.action_sync_orders()
            except Exception:
                _logger.exception("Lazada order sync failed for %s", config.name)

    @api.model
    def cron_push_stock(self):
        for config in self.search(
            [("active", "=", True), ("lazada_push_stock", "=", True)]
        ):
            try:
                config._push_stock_for_products()
            except Exception:
                _logger.exception("Lazada stock push failed for %s", config.name)

    @api.model
    def cron_sync_order_status(self):
        for config in self.search([("active", "=", True)]):
            try:
                config.sync_order_statuses()
            except Exception:
                _logger.exception(
                    "Lazada order status sync failed for %s", config.name
                )

    @api.model
    def cron_process_retry_queue(self):
        self.env["lazada.retry.queue"].cron_process()

    @api.model
    def cron_refresh_tokens(self):
        for config in self.search(
            [("active", "=", True), ("access_token", "!=", False)]
        ):
            try:
                config._ensure_valid_token()
            except Exception:
                _logger.exception("Lazada token refresh failed for %s", config.name)
