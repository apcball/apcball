import json
import logging
import secrets
import urllib.parse
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError

from .lazada_api import LazadaAPI, LazadaAPIError

_logger = logging.getLogger(__name__)

_MAX_PAGES = 40
_PAGE_SIZE = 50
# Order import walks long backfills in bounded windows.
_ORDER_WINDOW = timedelta(days=15)
_MANAGER = "lazada_connector.group_lazada_manager"


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
    app_secret = fields.Char(string="App Secret", required=True, copy=False,
                             groups=_MANAGER)
    seller_id = fields.Char(string="Seller ID")

    customer_partner_id = fields.Many2one(
        "res.partner",
        string="Marketplace Customer",
        check_company=True,
        help="Fallback partner for orders whose buyer cannot be mapped. "
        "Normally each Lazada buyer is mapped to a seller-specific contact.",
    )

    lazada_price_vat_rate = fields.Float(
        string="Remove VAT % from Lazada Prices",
        default=7.0,
        help="Lazada prices include VAT. Order line Unit Price = Lazada price "
        "/ (1 + rate/100). Set 0 to keep Lazada prices as they are.",
    )
    lazada_shipping_product_id = fields.Many2one(
        "product.product", string="Shipping Product",
        check_company=True,
        help="Product for the shipping fee line (paid by the buyer). Empty = "
        "the product with Internal Reference Service04.",
    )
    lazada_voucher_product_id = fields.Many2one(
        "product.product", string="Seller Voucher Product",
        check_company=True,
        help="Product for the seller voucher discount line. A product whose "
        "Internal Reference equals the voucher code is used first. Empty = "
        "created automatically.",
    )
    lazada_voucher_prefix = fields.Char(
        string="Seller Voucher Code Prefix", default="MOGEN",
        help="When Lazada does not say which voucher codes are the seller's, "
        "codes starting with this text are treated as the seller's own.",
    )
    lazada_ship_cutoff_hour = fields.Float(
        string="Delivery Cut-off Time",
        default=14.0,
        help="Orders paid before this time ship the same day, later ones the "
        "next day (sets the order's Delivery Date).",
    )

    redirect_url = fields.Char(
        string="Redirect URL",
        help="Must match the callback URL configured on the Lazada "
        "Open Platform app.",
    )
    oauth_state = fields.Char(readonly=True, copy=False, groups=_MANAGER)
    oauth_state_expires_at = fields.Datetime(readonly=True, copy=False)
    webhook_secret = fields.Char(
        string="Webhook Secret", copy=False, groups=_MANAGER,
        help="Optional secret used to validate webhook signatures. If empty, "
        "the app secret is used.",
    )

    access_token = fields.Char(readonly=True, copy=False, groups=_MANAGER)
    refresh_token = fields.Char(readonly=True, copy=False, groups=_MANAGER)
    token_expires_at = fields.Datetime(readonly=True, copy=False)

    temp_auth_code = fields.Char(
        string="Authorization Code", copy=False, groups=_MANAGER,
        help="After authorizing the seller, paste either the 'code' value or "
        "the whole redirect URL (contains ?code=...) here, then click "
        "'Exchange Token'.",
    )

    temp_access_token = fields.Char(
        string="Manual Access Token",
        copy=False,
        groups=_MANAGER,
        help="Optional: paste a token obtained elsewhere instead of using "
        "the OAuth flow.",
    )
    temp_refresh_token = fields.Char(
        string="Manual Refresh Token", copy=False, groups=_MANAGER
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
    lazada_push_price = fields.Boolean(
        string="Push Price to Lazada",
        default=False,
        help="Master switch. When on, this seller's linked products push "
        "their Odoo sales price back to Lazada (manual button or cron).",
    )
    lazada_warehouse_id = fields.Many2one(
        "stock.warehouse",
        string="Stock Source Warehouse",
        check_company=True,
        help="Warehouse whose free-to-use quantity is published to Lazada. "
        "Defaults to the company's main warehouse.",
    )
    lazada_stock_location_id = fields.Many2one(
        "stock.location",
        string="Stock Source Location",
        check_company=True,
        domain="[('usage', '=', 'internal'), "
        "('warehouse_id', '=', lazada_warehouse_id)]",
        help="Optional internal location (and its sub-locations) whose "
        "free-to-use quantity is published to Lazada. Leave empty to use "
        "the whole warehouse.",
    )

    last_stock_sync = fields.Datetime(readonly=True)
    last_stock_sync_unmapped = fields.Integer(
        string="Unmapped Lazada Listings", readonly=True,
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
    import_orders_to = fields.Datetime(
        string="Import Orders To",
        help="One-off backfill: when set together with Import Orders From, "
        "restricts the fetch to orders created up to this date instead of "
        "now, then clears this field.",
    )
    last_stock_push = fields.Datetime(readonly=True)
    last_price_push = fields.Datetime(readonly=True)
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

    @api.onchange("lazada_warehouse_id")
    def _onchange_lazada_warehouse_id(self):
        if (
            self.lazada_stock_location_id
            and self.lazada_stock_location_id.warehouse_id != self.lazada_warehouse_id
        ):
            self.lazada_stock_location_id = False

    @api.constrains("lazada_stock_location_id", "lazada_warehouse_id")
    def _check_lazada_stock_location(self):
        for config in self:
            location = config.lazada_stock_location_id
            if not location:
                continue
            if location.usage != "internal":
                raise ValidationError(
                    f"Stock Source Location '{location.display_name}' must be "
                    "an internal location."
                )
            if (
                config.lazada_warehouse_id
                and location.warehouse_id != config.lazada_warehouse_id
            ):
                raise ValidationError(
                    f"Stock Source Location '{location.display_name}' is not "
                    f"in warehouse '{config.lazada_warehouse_id.display_name}'."
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
        # A rejected log insert must never leave the business transaction aborted.
        with self.env.cr.savepoint():
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
        self.write({
            "oauth_state": state,
            "oauth_state_expires_at": fields.Datetime.now() + timedelta(minutes=10),
            "temp_auth_code": False,
        })
        url = api.get_authorization_url(self.redirect_url, state=state)
        return {
            "type": "ir.actions.act_url",
            "url": url,
            "target": "new",
        }

    def _accept_oauth_callback(self, state, code):
        """Consume a pending authorization once, including concurrent callbacks.

        ``state`` may be empty when Lazada does not echo it back; the caller
        then only routes to a single pending, unexpired authorization.
        """
        self.ensure_one()
        self.env.cr.execute("SELECT id FROM lazada_config WHERE id = %s FOR UPDATE", [self.id])
        self.invalidate_recordset(["oauth_state", "oauth_state_expires_at", "active"])
        if (not self.active or not code or not self.oauth_state
                or not self.oauth_state_expires_at
                or self.oauth_state_expires_at <= fields.Datetime.now()):
            return False
        if state and (not state.isascii()
                      or not secrets.compare_digest(self.oauth_state, state)):
            return False
        self.write({"oauth_state": False, "oauth_state_expires_at": False})
        return True

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
            self.write({"oauth_state": False, "oauth_state_expires_at": False,
                        "temp_auth_code": False})

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

    @classmethod
    def _sku_stock(cls, sku):
        """Available (sellable) stock of a /products/get SKU row."""
        for key in ("Available", "available", "quantity"):
            if sku.get(key) not in (None, ""):
                return cls._parse_int(sku.get(key))
        return 0

    @staticmethod
    def _sku_variant_name(sku):
        props = sku.get("saleProp")
        if isinstance(props, dict) and props:
            return ", ".join(str(value) for value in props.values() if value)
        return ", ".join(
            str(sku[key]) for key in ("color_family", "size") if sku.get(key)
        )

    # ------------------------------------------------------------------
    # Actions - Sync (Lazada -> Odoo, reference only)
    # ------------------------------------------------------------------
    def action_sync_stock(self):
        self.ensure_one()
        self = self.with_company(self.company_id).with_context(allowed_company_ids=self.company_id.ids)
        token = self._ensure_valid_token()
        api = self._get_api()
        Mapping = self.env["lazada.product.mapping"]

        offset = 0
        updated = 0
        unmapped = 0
        for _page in range(_MAX_PAGES):
            data = api.get_products(token, offset=offset) or {}
            products = data.get("products") or []
            if not products:
                break
            for product in products:
                item_id = product.get("item_id")
                item_name = (product.get("attributes") or {}).get("name")
                for sku in product.get("skus") or []:
                    seller_sku = sku.get("SellerSku") or sku.get("seller_sku")
                    if not seller_sku:
                        continue
                    mapping = Mapping.search([
                        ("lazada_config_id", "=", self.id),
                        ("seller_sku", "=", seller_sku),
                        ("active", "=", True),
                    ], limit=1)
                    record = mapping.product_id or Mapping.find_product_by_sku(
                        seller_sku
                    )
                    sku_id = sku.get("SkuId") or sku.get("sku_id")
                    stock_quantity = self._sku_stock(sku)
                    synced_at = fields.Datetime.now()
                    # Unmatched SKUs are kept as pending mappings so they can
                    # be linked to an Odoo product by hand.
                    mapping = Mapping.upsert(
                        self, seller_sku, record,
                        item_id=item_id, sku_id=sku_id,
                        lazada_stock=stock_quantity, stock_sync_at=synced_at,
                        item_name=item_name,
                        sku_name=self._sku_variant_name(sku),
                    )
                    # A mapping may already carry a product chosen by hand.
                    record = record or mapping.product_id
                    if not record:
                        unmapped += 1
                        _logger.warning(
                            "Lazada sync_stock (%s): item %s SKU %s (%r) is not "
                            "linked to an Odoo product - set the Odoo Internal "
                            "Reference or pick the product in Product Mappings.",
                            self.name, item_id, sku_id, seller_sku,
                        )
                        continue
                    record.write({
                        "lazada_item_id": str(item_id) if item_id else False,
                        "lazada_sku_id": str(sku_id) if sku_id else False,
                        "lazada_stock": stock_quantity,
                        "lazada_last_sync": synced_at,
                    })
                    updated += 1
            if len(products) < _PAGE_SIZE:
                break
            offset += len(products)

        self.write({
            "last_stock_sync": fields.Datetime.now(),
            "last_stock_sync_unmapped": unmapped,
        })
        _logger.info("Lazada stock sync (%s): %s products updated, %s unmapped",
                     self.name, updated, unmapped)
        return updated

    def action_sync_stock_button(self):
        """Form button: run the stock pull and report what was not linked."""
        self.ensure_one()
        updated = self.action_sync_stock()
        message = f"{updated} product(s) updated from Lazada."
        if self.last_stock_sync_unmapped:
            message += (
                f" {self.last_stock_sync_unmapped} Lazada listing(s) are not "
                "linked to an Odoo product: set a SellerSku on Lazada matching "
                "the Odoo Internal Reference, or pick the product in "
                "Lazada > Product Mappings."
            )
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lazada stock sync",
                "message": message,
                "type": "warning" if self.last_stock_sync_unmapped else "success",
                "sticky": bool(self.last_stock_sync_unmapped),
            },
        }

    def action_sync_orders(self):
        """Import new Lazada orders.

        Normally from the last sync up to now. When "Import Orders From" is
        set, from that date instead; "Import Orders To" additionally caps the
        upper bound (both are a one-off backfill window, cleared afterwards).
        Long periods are fetched in windows.
        """
        self.ensure_one()
        self = self.with_company(self.company_id).with_context(allowed_company_ids=self.company_id.ids)
        token = self._ensure_valid_token()
        api = self._get_api()

        now = fields.Datetime.now()
        sync_from = self.import_orders_from or self.last_order_sync or (
            now - timedelta(days=2)
        )
        sync_to = self.import_orders_to or now
        if sync_to > now:
            sync_to = now
        if sync_from >= sync_to:
            if self.import_orders_from or self.import_orders_to:
                raise UserError("Import Orders From must be before Import Orders To.")
            return 0  # nothing new since the last sync (same second)
        created = 0
        window_start = sync_from
        while window_start < sync_to:
            window_end = min(window_start + _ORDER_WINDOW, sync_to)
            created += self._sync_orders_window(api, token, window_start, window_end)
            window_start = window_end

        # The next run starts where this window ends, so orders created while
        # this sync is running are not skipped.
        self.write({
            "last_order_sync": sync_to,
            "import_orders_from": False,
            "import_orders_to": False,
        })
        _logger.info("Lazada order sync (%s): %s new orders created",
                     self.name, created)
        return created

    def _sync_orders_window(self, api, token, created_after, created_before):
        """Import the orders created between two (naive UTC) datetimes."""
        SaleOrder = self.env["sale.order"]
        created = 0
        offset = 0
        for _page in range(_MAX_PAGES):
            data = api.get_orders(
                token, created_after, created_before=created_before,
                offset=offset, limit=_PAGE_SIZE,
            ) or {}
            orders = data.get("orders") or []
            if not isinstance(orders, list):
                raise UserError("Lazada returned an invalid order list. Sync was not advanced.")
            for entry in orders:
                order_id = str(entry.get("order_id") or "").strip()
                if not order_id:
                    raise UserError("Lazada returned an order without an id. Sync was not advanced.")
                existing = SaleOrder.search([
                    ("lazada_config_id", "=", self.id),
                    ("lazada_order_id", "=", order_id),
                ], limit=1)
                if existing:
                    continue
                try:
                    with self.env.cr.savepoint():
                        SaleOrder.create_from_lazada(order_id, config=self)
                    created += 1
                except Exception as exc:
                    self.env["lazada.retry.queue"].enqueue(
                        self, "sync_order",
                        {"order_id": order_id},
                        str(exc),
                    )
            if len(orders) < _PAGE_SIZE:
                return created
            offset += len(orders)
        raise UserError("Lazada order pagination limit reached. Sync was not advanced; use a smaller date range.")

    def action_sync_orders_button(self):
        """Form button: import orders and report how many were created."""
        self.ensure_one()
        created = self.action_sync_orders()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lazada orders",
                "message": f"{created} new order(s) imported from Lazada.",
                "type": "success",
                "sticky": False,
            },
        }

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
        """Refresh statuses: the latest 200 orders, or exactly ``order_ids``.

        Explicit ids (webhook, retry queue) raise on failure so the caller's
        retry/backoff handles them; the periodic run queues each failure.
        """
        self.ensure_one()
        token = self._ensure_valid_token()
        SaleOrder = self.env["sale.order"]
        domain = [("is_lazada_order", "=", True),
                  ("lazada_config_id", "=", self.id)]
        if order_ids is not None:
            order_ids = [str(order_id) for order_id in order_ids]
            domain.append(("lazada_order_id", "in", order_ids))
        orders = SaleOrder.search(
            domain, order="id desc", limit=200 if order_ids is None else None,
        )
        if order_ids is not None and set(order_ids) - set(orders.mapped("lazada_order_id")):
            raise UserError("Import the missing Lazada order before syncing its status.")
        updated = 0
        api = self._get_api()
        for order in orders:
            if order_ids is not None:
                order.refresh_lazada_status(api=api, token=token)
                updated += 1
                continue
            try:
                with self.env.cr.savepoint():
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

    # ------------------------------------------------------------------
    # Webhooks
    # ------------------------------------------------------------------
    @staticmethod
    def _webhook_data(payload):
        """The event body; Lazada may wrap it as a JSON string in "message"."""
        data = payload.get("data", payload)
        message = data.get("message") if isinstance(data, dict) else None
        if isinstance(message, str):
            try:
                message = json.loads(message)
            except ValueError:
                message = None
        if isinstance(message, dict):
            data = message
        return data if isinstance(data, dict) else {}

    @classmethod
    def _webhook_order_id(cls, payload):
        data = cls._webhook_data(payload)
        return data.get("trade_order_id") or data.get("order_id") or data.get("OrderId")

    @classmethod
    def _webhook_operation(cls, payload):
        """"sync_order" (new order or status change), "sync_stock" or None.

        Lazada trade-order pushes carry ``message_type`` 0.
        """
        data = cls._webhook_data(payload)
        event = str(
            payload.get("event_type") or payload.get("type")
            or data.get("type") or ""
        ).upper()
        if str(payload.get("message_type")) == "0" or "ORDER" in event or "STATUS" in event:
            return "sync_order"
        if "STOCK" in event or "SKU" in event:
            return "sync_stock"
        return None

    def process_webhook(self, payload):
        self.ensure_one()
        operation = self._webhook_operation(payload)
        order_id = self._webhook_order_id(payload)
        if operation == "sync_order" and order_id:
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
        if operation == "sync_stock":
            self.action_sync_stock()
            return "sku_stock_update"
        return "ignored"

    # ------------------------------------------------------------------
    # Actions - Push stock (Odoo -> Lazada)
    # ------------------------------------------------------------------
    def _lazada_stock_context(self):
        """Context giving product.free_qty for the stock published to Lazada."""
        self.ensure_one()
        if self.lazada_stock_location_id:
            # Odoo's 'location' context also counts child locations.
            return {"location": self.lazada_stock_location_id.id}
        warehouse = self.lazada_warehouse_id or self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not warehouse:
            raise UserError("No warehouse available for stock push.")
        return {"warehouse": warehouse.id}

    def _check_products_company(self, products, what):
        if any(product.company_id and product.company_id != self.company_id for product in products):
            raise UserError(f"Cannot push another company's {what} to this seller.")

    def _linked_target(self, Mapping, product):
        """(mapping, item_id, sku_id, seller_sku) of a product for this seller."""
        mapping = Mapping.search([
            ("lazada_config_id", "=", self.id),
            ("product_id", "=", product.id),
            ("active", "=", True),
        ], limit=1)
        item_id = (mapping.lazada_item_id if mapping else False) or product.lazada_item_id
        sku_id = (mapping.lazada_sku_id if mapping else False) or product.lazada_sku_id
        # The mapping keeps Lazada's own spelling of a case-insensitive match.
        seller_sku = (mapping.seller_sku if mapping else False) or product.default_code
        return mapping, item_id, sku_id, seller_sku

    def _push_stock_for_products(self, products=None, force=False):
        """Push free-to-use qty to Lazada for the given (or all linked) products.

        ``force`` (Product Mapping button): push even when the product is not
        flagged for stock sync, the qty is unchanged or above the refill
        threshold. Returns the number of successful SKU updates.
        """
        self.ensure_one()
        self = self.with_company(self.company_id).with_context(allowed_company_ids=self.company_id.ids)
        if products is not None:
            products = products.with_env(self.env)
            self._check_products_company(products, "stock")
        if not self.lazada_push_stock:
            raise UserError(
                f"Seller '{self.name}': 'Push Stock to Lazada' is not enabled."
            )
        token = self._ensure_valid_token()
        api = self._get_api()
        stock_context = self._lazada_stock_context()

        Mapping = self.env["lazada.product.mapping"]
        if products is not None:
            targets = products if force else products.filtered(lambda p: p.lazada_sync_stock_out)
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

        # Variants of one Lazada item go out in a single update call.
        entries = []
        for product in targets.with_context(**stock_context):
            mapping, item_id, sku_id, seller_sku = self._linked_target(Mapping, product)
            qty = int(max(product.free_qty, 0))
            if mapping:
                qty = mapping._lazada_push_qty(qty)
            already_pushed = (
                mapping.last_pushed_stock if mapping else product.lazada_pushed_stock
            )
            pushed_at = mapping.last_stock_push if mapping else product.lazada_stock_push_date
            lazada_stock = mapping.lazada_stock if mapping else product.lazada_stock
            # Skip only when Lazada still shows what we last pushed; if the
            # stock changed on Lazada (orders, manual edits) push it back.
            if not force:
                if qty == already_pushed and qty == lazada_stock and pushed_at:
                    continue
                # Refill rule: only top Lazada up once it runs low.
                if mapping and mapping.refill_below and lazada_stock >= mapping.refill_below:
                    continue
            if not item_id or not seller_sku:
                continue
            entries.append({
                "product": product, "mapping": mapping, "qty": qty,
                "item_id": item_id, "sku_id": sku_id, "seller_sku": seller_sku,
            })

        by_item = {}
        for entry in entries:
            by_item.setdefault(entry["item_id"], []).append(entry)

        pushed = 0
        failures = []
        for item_entries in by_item.values():
            try:
                api.update_stock_batch(token, [{
                    "seller_sku": entry["seller_sku"], "sku_id": entry["sku_id"],
                    "item_id": entry["item_id"], "quantity": entry["qty"],
                } for entry in item_entries])
            except LazadaAPIError as exc:
                for entry in item_entries:
                    failures.append(f"{entry['seller_sku']}: {exc}")
                    self.env["lazada.retry.queue"].enqueue(
                        self, "push_stock", {"product_id": entry["product"].id}, str(exc)
                    )
                    _logger.warning("Lazada stock push failed for %s: %s",
                                    entry["seller_sku"], exc)
                continue
            for entry in item_entries:
                now = fields.Datetime.now()
                entry["product"].write({
                    "lazada_pushed_stock": entry["qty"],
                    "lazada_stock": entry["qty"],
                    "lazada_stock_push_date": now,
                })
                if entry["mapping"]:
                    entry["mapping"].write({
                        "last_pushed_stock": entry["qty"],
                        "lazada_stock": entry["qty"],
                        "last_stock_push": now,
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
    # Actions - Push price (Odoo -> Lazada)
    # ------------------------------------------------------------------
    def _push_price_for_products(self, products=None, force=False):
        """Push sales price to Lazada for the given (or all linked) products.

        Same shape as ``_push_stock_for_products``. ``force`` (Product Mapping
        button): push even when the price hasn't changed. Returns the number
        of successful price updates.
        """
        self.ensure_one()
        self = self.with_company(self.company_id).with_context(allowed_company_ids=self.company_id.ids)
        if products is not None:
            products = products.with_env(self.env)
            self._check_products_company(products, "price")
        if not self.lazada_push_price:
            raise UserError(
                f"Seller '{self.name}': 'Push Price to Lazada' is not enabled."
            )
        token = self._ensure_valid_token()
        api = self._get_api()

        Mapping = self.env["lazada.product.mapping"]
        if products is not None:
            targets = products if force else products.filtered(lambda p: p.lazada_sync_price_out)
        else:
            mapped_products = Mapping.search([
                ("lazada_config_id", "=", self.id),
                ("active", "=", True),
                ("product_id.lazada_sync_price_out", "=", True),
            ]).mapped("product_id")
            targets = self.env["product.product"].search([
                ("lazada_item_id", "!=", False),
                ("lazada_sync_price_out", "=", True),
            ]) | mapped_products

        entries = []
        for product in targets:
            mapping, item_id, sku_id, seller_sku = self._linked_target(Mapping, product)
            price = product.lst_price
            already_pushed = (
                mapping.last_pushed_price if mapping else product.lazada_pushed_price
            )
            pushed_at = mapping.last_price_push if mapping else product.lazada_price_push_date
            if not force and price == already_pushed and pushed_at:
                continue
            if not item_id or not seller_sku:
                continue
            entries.append({
                "product": product, "mapping": mapping, "price": price,
                "item_id": item_id, "sku_id": sku_id, "seller_sku": seller_sku,
            })

        by_item = {}
        for entry in entries:
            by_item.setdefault(entry["item_id"], []).append(entry)

        pushed = 0
        failures = []
        for item_entries in by_item.values():
            try:
                api.update_price(token, [{
                    "seller_sku": entry["seller_sku"], "sku_id": entry["sku_id"],
                    "item_id": entry["item_id"], "price": entry["price"],
                } for entry in item_entries])
            except LazadaAPIError as exc:
                for entry in item_entries:
                    failures.append(f"{entry['seller_sku']}: {exc}")
                    self.env["lazada.retry.queue"].enqueue(
                        self, "push_price", {"product_id": entry["product"].id}, str(exc)
                    )
                    _logger.warning("Lazada price push failed for %s: %s",
                                    entry["seller_sku"], exc)
                continue
            for entry in item_entries:
                now = fields.Datetime.now()
                entry["product"].write({
                    "lazada_pushed_price": entry["price"],
                    "lazada_price": entry["price"],
                    "lazada_price_push_date": now,
                })
                if entry["mapping"]:
                    entry["mapping"].write({
                        "last_pushed_price": entry["price"],
                        "last_price_push": now,
                    })
                pushed += 1

        self.last_price_push = fields.Datetime.now()
        _logger.info("Lazada price push (%s): %s ok, %s failed",
                     self.name, pushed, len(failures))
        if failures and products is not None:
            raise UserError(
                "Some price pushes failed:\n" + "\n".join(failures[:20])
            )
        return pushed

    def action_push_price(self):
        self.ensure_one()
        pushed = self._push_price_for_products()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Lazada price push",
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
    def cron_push_price(self):
        for config in self.search(
            [("active", "=", True), ("lazada_push_price", "=", True)]
        ):
            try:
                config._push_price_for_products()
            except Exception:
                _logger.exception("Lazada price push failed for %s", config.name)

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
