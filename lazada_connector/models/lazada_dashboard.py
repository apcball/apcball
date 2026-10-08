from datetime import datetime, timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

PERIODS = (1, 7, 30)
MIN_SERIES_DAYS = 7
STALE_PUSH_HOURS = 24
STOCK_OPERATIONS = ("push_stock", "sync_stock")


class LazadaDashboard(models.AbstractModel):
    _name = "lazada.dashboard"
    _description = "Lazada Ops Health Dashboard"

    def _check_access(self):
        if self.env.su:
            return
        if not self.env.user.has_group("lazada_connector.group_lazada_user"):
            raise AccessError(_("Lazada User access is required."))

    @api.model
    def _normalize_filters(self, shop_ids, days):
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = 7
        if days not in PERIODS:
            days = 7
        shops = self.env["lazada.config"].sudo().search(
            [("company_id", "in", self.env.companies.ids)]
        )
        if shop_ids:
            wanted = {int(sid) for sid in shop_ids if str(sid).isdigit()}
            selected = shops.filtered(lambda s: s.id in wanted) or shops
        else:
            selected = shops
        return shops, selected, days

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @api.model
    def _day_buckets(self, series_days):
        today = fields.Date.context_today(self)
        return [today - timedelta(days=i) for i in range(series_days - 1, -1, -1)]

    @api.model
    def _daily_counts(self, model, domain, date_field, buckets, extra_group=None):
        """Counts per day (user tz) for `buckets`; with `extra_group` returns
        {group_value: [count per bucket]}."""
        groupby = [f"{date_field}:day"] + ([extra_group] if extra_group else [])
        index = {day: i for i, day in enumerate(buckets)}
        rows = model._read_group(domain, groupby, ["__count"])
        if not extra_group:
            series = [0] * len(buckets)
            for day, count in rows:
                day = day.date() if isinstance(day, datetime) else day
                if day in index:
                    series[index[day]] += count
            return series
        series = {}
        for day, group, count in rows:
            day = day.date() if isinstance(day, datetime) else day
            if day in index:
                series.setdefault(group, [0] * len(buckets))[index[day]] += count
        return series

    @staticmethod
    def _delta(current, previous):
        """Percent change vs previous period; None when there is no baseline."""
        if not previous:
            return None if not current else {"pct": None, "dir": "up"}
        pct = round((current - previous) * 100.0 / previous)
        return {"pct": abs(pct), "dir": "up" if pct > 0 else "down" if pct < 0 else "flat"}

    @staticmethod
    def _window_domain(field, start, end):
        return [(field, ">=", fields.Datetime.to_string(start)),
                (field, "<", fields.Datetime.to_string(end))]

    # ------------------------------------------------------------------
    # main
    # ------------------------------------------------------------------
    @api.model
    def get_dashboard_data(self, shop_ids=None, days=7):
        self._check_access()
        all_shops, shops, days = self._normalize_filters(shop_ids, days)
        env = self.env
        now = fields.Datetime.now()
        since_dt = now - timedelta(days=days)
        prev_dt = since_dt - timedelta(days=days)
        since = fields.Datetime.to_string(since_dt)
        stale_before = fields.Datetime.to_string(now - timedelta(hours=STALE_PUSH_HOURS))
        buckets = self._day_buckets(max(days, MIN_SERIES_DAYS))
        shop_dom = [("lazada_config_id", "in", shops.ids)]

        Log = env["lazada.api.log"].sudo()
        Queue = env["lazada.retry.queue"].sudo()
        Mapping = env["lazada.product.mapping"].sudo()
        Job = env["lazada.fulfillment.job"].sudo()
        Order = env["sale.order"].sudo()

        def event_tile(model, base_dom, date_field, value, action, domain, severity,
                       label, **extra):
            """Tile whose trend/delta come from records *created* per day."""
            cur = model.search_count(base_dom + self._window_domain(date_field, since_dt, now))
            prev = model.search_count(base_dom + self._window_domain(date_field, prev_dt, since_dt))
            return {
                "value": value, "action": action, "domain": domain, "severity": severity,
                "label": label, "delta": self._delta(cur, prev),
                "series": self._daily_counts(model, base_dom + [(date_field, ">=", fields.Datetime.to_string(
                    datetime.combine(buckets[0], datetime.min.time()) - timedelta(days=1)))],
                    date_field.split(":")[0], buckets),
                **extra,
            }

        # ---- tiles ----
        err_base = shop_dom + [("status", "=", "error")]
        err_dom = err_base + [("create_date", ">=", since)]
        errors = dict(Log._read_group(err_dom, ["log_type"], ["__count"]))
        err_total = sum(errors.values())
        avg = Log._read_group(
            shop_dom + [("log_type", "=", "request"), ("create_date", ">=", since)],
            [], ["duration_ms:avg"],
        )
        avg_ms = int(avg[0][0] or 0) if avg else 0

        q_states = dict(Queue._read_group(shop_dom, ["state"], ["__count"]))
        failed_dom = shop_dom + [("state", "=", "failed")]
        stock_failed_dom = failed_dom + [("operation_type", "in", STOCK_OPERATIONS)]
        stock_failed = Queue.search_count(stock_failed_dom)

        unmapped_dom = shop_dom + [("product_id", "=", False)]
        unmapped = Mapping.search_count(unmapped_dom)
        stale_dom = shop_dom + [
            ("product_id", "!=", False),
            "|", ("last_stock_push", "=", False), ("last_stock_push", "<", stale_before),
        ]
        stale = Mapping.search_count(stale_dom)

        job_dom = [("config_id", "in", shops.ids), ("state", "in", ("uncertain", "error"))]
        jobs = Job.search_count(job_dom)

        tiles = {
            "api_errors": event_tile(
                Log, err_base, "create_date", err_total,
                "lazada_connector.action_lazada_api_log", err_dom,
                "bad" if err_total else "ok", _("API Errors"),
                request=errors.get("request", 0), webhook=errors.get("webhook", 0),
                avg_ms=avg_ms),
            "retry_failed": event_tile(
                Queue, failed_dom, "create_date", q_states.get("failed", 0),
                "lazada_connector.action_lazada_retry_queue", failed_dom,
                "warn" if q_states.get("failed") else "ok", _("Retry Failed"),
                pending=q_states.get("pending", 0)),
            "stock_failed": event_tile(
                Queue, stock_failed_dom, "create_date", stock_failed,
                "lazada_connector.action_lazada_retry_queue", stock_failed_dom,
                "bad" if stock_failed else "ok", _("Stock Sync Failed")),
            "unmapped": event_tile(
                Mapping, unmapped_dom, "create_date", unmapped,
                "lazada_connector.action_lazada_product_mapping", unmapped_dom,
                "warn" if unmapped else "ok", _("Unmapped Listings")),
            "stale_push": {
                "value": stale, "action": "lazada_connector.action_lazada_product_mapping",
                "domain": stale_dom, "severity": "warn" if stale else "ok",
                "label": _("No Stock Push in 24h"), "delta": None, "series": [],
            },
            "fulfillment": event_tile(
                Job, job_dom, "create_date", jobs,
                "lazada_connector.action_lazada_fulfillment_jobs", job_dom,
                "bad" if jobs else "ok", _("Shipments Need Attention")),
        }

        # ---- orders ----
        order_base = [("is_lazada_order", "=", True), ("lazada_config_id", "in", shops.ids)]
        order_dom = order_base + [("date_order", ">=", since)]
        o_groups = Order._read_group(order_dom, ["lazada_order_status"], ["__count"])
        total_orders = sum(count for _status, count in o_groups)
        by_status = sorted(
            ({"status": status or "unknown", "count": count,
              "pct": round(count * 100.0 / total_orders, 1) if total_orders else 0}
             for status, count in o_groups),
            key=lambda row: -row["count"],
        )
        prev_orders = Order.search_count(
            order_base + self._window_domain("date_order", prev_dt, since_dt))
        order_trend = self._daily_counts(
            Order,
            order_base + [("date_order", ">=", fields.Datetime.to_string(
                datetime.combine(buckets[0], datetime.min.time()) - timedelta(days=1)))],
            "date_order", buckets)

        # ---- sync health (API requests) ----
        req_base = shop_dom + [("log_type", "=", "request")]
        req_dom = req_base + [("create_date", ">=", fields.Datetime.to_string(
            datetime.combine(buckets[0], datetime.min.time()) - timedelta(days=1)))]
        by_day = self._daily_counts(Log, req_dom, "create_date", buckets, extra_group="status")
        zeros = [0] * len(buckets)
        ok_series, fail_series = by_day.get("success", zeros), by_day.get("error", zeros)
        window = Log._read_group(
            req_base + [("create_date", ">=", since)], ["status"], ["__count"])
        window = dict(window)
        ok_total, fail_total = window.get("success", 0), window.get("error", 0)
        req_total = ok_total + fail_total

        # ---- shop rows / crons ----
        def shop_status(shop):
            if not shop.token_expires_at:
                return "no_token"
            return "expired" if shop.token_expires_at <= now else "active"

        crons = env["ir.cron"].sudo().search([
            ("ir_actions_server_id.model_id.model", "in", [
                "lazada.config", "lazada.retry.queue", "lazada.fulfillment.job",
                "sale.order", "lazada.product.mapping",
            ]),
            ("name", "ilike", "Lazada"),
        ], order="name")

        return {
            "days": days,
            "periods": list(PERIODS),
            "dates": [d.isoformat() for d in buckets],
            "shops": [{"id": s.id, "name": s.name} for s in all_shops],
            "selected_shop_ids": shops.ids,
            "tiles": tiles,
            "orders": {
                "total": total_orders,
                "delta": self._delta(total_orders, prev_orders),
                "by_status": by_status,
                "trend": order_trend,
                "action": "lazada_connector.action_lazada_orders",
                "domain": order_dom,
            },
            "sync": {
                "ok": ok_total, "failed": fail_total,
                "rate": round(ok_total * 100.0 / req_total, 1) if req_total else None,
                "ok_series": ok_series, "failed_series": fail_series,
                "action": "lazada_connector.action_lazada_api_log",
                "domain": req_base + [("create_date", ">=", since)],
            },
            "shop_rows": [
                {
                    "id": s.id, "name": s.name, "status": shop_status(s),
                    "last_stock_sync": fields.Datetime.to_string(s.last_stock_sync)
                    if s.last_stock_sync else False,
                    "unmapped_at_sync": s.last_stock_sync_unmapped,
                }
                for s in shops
            ],
            "crons": [
                {"name": c.name, "active": c.active,
                 "nextcall": fields.Datetime.to_string(c.nextcall) if c.nextcall else False}
                for c in crons
            ],
        }
