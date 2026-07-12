import hashlib
import json

from psycopg2 import IntegrityError

from odoo import api, fields, models


class SalesAnalyticsCache(models.Model):
    _name = "buz.sales.analytics.cache"
    _description = "Sales Analytics Cache"
    _log_access = False

    cache_key = fields.Char(required=True, index=True)
    cache_data = fields.Text()
    date_computed = fields.Datetime()
    is_valid = fields.Boolean(default=True)
    ttl_minutes = fields.Integer(default=30)

    _sql_constraints = [
        ("cache_key_unique", "UNIQUE(cache_key)", "Cache key must be unique"),
    ]

    @api.model
    def _make_key(self, params):
        # Scope by company so identical filters in different companies
        # never share cache entries.
        raw = json.dumps(
            {"company_id": self.env.company.id, "params": params},
            sort_keys=True,
            default=str,
        )
        return hashlib.md5(raw.encode()).hexdigest()

    @api.model
    def get_cached(self, key):
        record = self.sudo().search([("cache_key", "=", key), ("is_valid", "=", True)], limit=1)
        if not record:
            return None
        if not record.date_computed:
            return None
        elapsed = (fields.Datetime.now() - record.date_computed).total_seconds() / 60.0
        if elapsed > record.ttl_minutes:
            record.is_valid = False
            return None
        try:
            return json.loads(record.cache_data)
        except (json.JSONDecodeError, TypeError):
            return None

    @api.model
    def set_cached(self, key, data, ttl=30):
        vals = {
            "cache_data": json.dumps(data, default=str),
            "date_computed": fields.Datetime.now(),
            "is_valid": True,
            "ttl_minutes": ttl,
        }
        existing = self.sudo().search([("cache_key", "=", key)], limit=1)
        if existing:
            existing.write(vals)
        else:
            try:
                with self.env.cr.savepoint():
                    self.sudo().create(dict(vals, cache_key=key))
            except IntegrityError:
                # Concurrent request created the same key first.
                existing = self.sudo().search([("cache_key", "=", key)], limit=1)
                if existing:
                    existing.write(vals)
        return data

    @api.model
    def invalidate_key(self, key):
        self.sudo().search([("cache_key", "=", key)]).write({"is_valid": False})

    @api.model
    def invalidate_all(self):
        self.sudo().search([]).write({"is_valid": False})
        self.sudo().search([("is_valid", "=", False)]).unlink()

    @api.model
    def _purge_stale(self, keep_keys=None):
        keep_keys = keep_keys or []
        stale = self.sudo().search([("is_valid", "=", False), ("cache_key", "not in", keep_keys)])
        expired = self.sudo().search([
            ("is_valid", "=", True),
            ("cache_key", "not in", keep_keys),
        ]).filtered(
            lambda r: not r.date_computed
            or (fields.Datetime.now() - r.date_computed).total_seconds() / 60.0 > r.ttl_minutes
        )
        (stale | expired).unlink()

    @api.model
    def cron_refresh_cache(self):
        dashboard = self.env["buz.sales.analytics.dashboard"]
        default_filters = dashboard._sanitize_filters(dashboard._get_default_filters())
        key = self._make_key(default_filters)
        data = dashboard._compute_dashboard_data(default_filters)
        self.set_cached(key, data, ttl=60)
        prev_filters = dashboard._sanitize_filters(dashboard._get_previous_period_filters())
        prev_key = self._make_key(prev_filters)
        prev_data = dashboard._compute_dashboard_data(prev_filters)
        self.set_cached(prev_key, prev_data, ttl=60)
        self._purge_stale(keep_keys=[key, prev_key])
