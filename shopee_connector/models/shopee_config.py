import logging
import time
import urllib.parse
from datetime import timedelta

from odoo import api, fields, models
from odoo.exceptions import UserError

from .shopee_api import ShopeeAPI, ShopeeAPIError

_logger = logging.getLogger(__name__)

_MAX_PAGES = 40


class ShopeeConfig(models.Model):
    _name = "shopee.config"
    _description = "Shopee Shop Connection"
    _check_company_auto = True

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
    partner_key = fields.Char(string="Partner Key", required=True)
    shop_id = fields.Char(string="Shop ID")

    customer_partner_id = fields.Many2one(
        "res.partner",
        string="Marketplace Customer",
        check_company=True,
        help="Draft Sale Orders imported from Shopee are billed to this "
        "partner. The real buyer name goes to 'Customer Reference' and the "
        "recipient address to the order notes.",
    )

    redirect_url = fields.Char(
        string="Redirect URL",
        help="Must match the Test/Live Redirect URL Domain configured on "
        "the Shopee Open Platform app.",
    )

    access_token = fields.Char(readonly=True, copy=False)
    refresh_token = fields.Char(readonly=True, copy=False)
    token_expires_at = fields.Datetime(readonly=True, copy=False)

    temp_auth_code = fields.Char(
        string="Authorization Code",
        help="After authorizing the shop, paste either the 'code' value or "
        "the whole redirect URL (contains ?code=...&shop_id=...) here, then "
        "click 'Exchange Token'. Code expires after ~10 minutes.",
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

    last_stock_sync = fields.Datetime(readonly=True)
    last_order_sync = fields.Datetime(readonly=True)
    last_stock_push = fields.Datetime(readonly=True)

    @api.onchange("company_id")
    def _onchange_company_id(self):
        if self.company_id and (
            not self.shopee_warehouse_id
            or self.shopee_warehouse_id.company_id != self.company_id
        ):
            self.shopee_warehouse_id = self.env["stock.warehouse"].search(
                [("company_id", "=", self.company_id.id)], limit=1
            )

    # ------------------------------------------------------------------
    def _get_api(self):
        self.ensure_one()
        return ShopeeAPI(
            partner_id=self.partner_id,
            partner_key=self.partner_key,
            shop_id=self.shop_id,
            environment=self.environment,
        )

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
                "refresh_token": resp["refresh_token"],
                # Shopee access_token is valid 4h; refresh a bit early
                "token_expires_at": fields.Datetime.now()
                + timedelta(seconds=resp.get("expire_in", 14400) - 120),
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
        url = api.get_authorization_url(self.redirect_url)
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
        self.write({"shop_id": str(shop_id)})
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

    # ------------------------------------------------------------------
    # Actions - Sync (Shopee -> Odoo, reference only)
    # ------------------------------------------------------------------
    def action_sync_stock(self):
        self.ensure_one()
        token = self._ensure_valid_token()
        api = self._get_api()
        Product = self.env["product.product"]

        offset = 0
        updated = 0
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
                    model_resp = api.get_model_list(token, item_id)
                    for model in model_resp.get("response", {}).get("model", []):
                        sku = model.get("model_sku")
                        if not sku:
                            continue
                        product = Product.search(
                            [("default_code", "=", sku)], limit=1
                        )
                        if not product:
                            continue
                        product.write({
                            "shopee_item_id": str(item_id),
                            "shopee_model_id": str(model["model_id"]),
                            "shopee_stock": self._model_seller_stock(
                                model.get("stock_info_v2")
                            ),
                            "shopee_last_sync": fields.Datetime.now(),
                        })
                        updated += 1
                else:
                    sku = item.get("item_sku")
                    if not sku:
                        continue
                    product = Product.search(
                        [("default_code", "=", sku)], limit=1
                    )
                    if not product:
                        continue
                    product.write({
                        "shopee_item_id": str(item_id),
                        "shopee_model_id": False,
                        "shopee_stock": self._model_seller_stock(
                            item.get("stock_info_v2")
                        ),
                        "shopee_last_sync": fields.Datetime.now(),
                    })
                    updated += 1

            if not item_data.get("has_next_page"):
                break
            offset = item_data.get("next_offset", offset + len(items))

        self.last_stock_sync = fields.Datetime.now()
        _logger.info("Shopee stock sync (%s): %s products updated",
                     self.name, updated)
        return updated

    def action_sync_orders(self):
        self.ensure_one()
        if not self.customer_partner_id:
            raise UserError(
                f"Shop '{self.name}': set a 'Marketplace Customer' before "
                "syncing orders."
            )
        token = self._ensure_valid_token()
        api = self._get_api()
        SaleOrder = self.env["sale.order"]

        time_to = int(time.time())
        time_from = time_to - 24 * 60 * 60  # last 24h; widen if needed

        cursor = ""
        created = 0
        seen_cursors = set()
        for _page in range(_MAX_PAGES):
            list_resp = api.get_order_list(token, time_from, time_to, cursor)
            resp = list_resp.get("response", {})
            order_sns = [o["order_sn"] for o in resp.get("order_list", [])]
            if order_sns:
                detail_resp = api.get_order_detail(token, order_sns)
                for shopee_order in detail_resp.get("response", {}).get(
                    "order_list", []
                ):
                    existing = SaleOrder.search(
                        [("shopee_order_sn", "=", shopee_order["order_sn"])], limit=1
                    )
                    if existing:
                        continue
                    SaleOrder.create_from_shopee(
                        shopee_order, partner=self.customer_partner_id
                    )
                    created += 1

            if not resp.get("more"):
                break
            cursor = resp.get("next_cursor", "")
            if not cursor or cursor in seen_cursors:
                break
            seen_cursors.add(cursor)

        self.last_order_sync = fields.Datetime.now()
        _logger.info("Shopee order sync (%s): %s new orders created",
                     self.name, created)
        return created

    # ------------------------------------------------------------------
    # Actions - Push stock (Odoo -> Shopee)
    # ------------------------------------------------------------------
    def _push_stock_for_products(self, products=None):
        """Push free-to-use qty to Shopee for the given (or all linked) products.

        Returns the number of successful update_stock calls.
        """
        self.ensure_one()
        if not self.shopee_push_stock:
            raise UserError(
                f"Shop '{self.name}': 'Push Stock to Shopee' is not enabled."
            )
        token = self._ensure_valid_token()
        api = self._get_api()
        warehouse = self.shopee_warehouse_id or self.env["stock.warehouse"].search(
            [("company_id", "=", self.company_id.id)], limit=1
        )
        if not warehouse:
            raise UserError("No warehouse available for stock push.")

        domain = [
            ("shopee_item_id", "!=", False),
            ("shopee_sync_stock_out", "=", True),
        ]
        targets = products if products is not None else self.env["product.product"].search(domain)
        if products is not None:
            targets = targets.filtered(
                lambda p: p.shopee_item_id and p.shopee_sync_stock_out
            )

        pushed = 0
        failures = []
        for product in targets.with_context(warehouse=warehouse.id):
            qty = int(max(product.free_qty, 0))
            if qty == product.shopee_pushed_stock and product.shopee_stock_push_date:
                continue
            try:
                api.update_stock(
                    token,
                    int(product.shopee_item_id),
                    int(product.shopee_model_id) if product.shopee_model_id else 0,
                    qty,
                )
            except ShopeeAPIError as exc:
                failures.append(f"{product.default_code or product.display_name}: {exc}")
                _logger.warning("Shopee stock push failed for %s: %s",
                                product.default_code, exc)
                continue
            product.write({
                "shopee_pushed_stock": qty,
                "shopee_stock_push_date": fields.Datetime.now(),
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
    def cron_refresh_tokens(self):
        for config in self.search(
            [("active", "=", True), ("access_token", "!=", False)]
        ):
            try:
                config._ensure_valid_token()
            except Exception:
                _logger.exception("Shopee token refresh failed for %s", config.name)
