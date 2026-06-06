import hashlib
import json

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
        raw = json.dumps(params, sort_keys=True, default=str)
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
        existing = self.sudo().search([("cache_key", "=", key)], limit=1)
        vals = {
            "cache_data": json.dumps(data, default=str),
            "date_computed": fields.Datetime.now(),
            "is_valid": True,
            "ttl_minutes": ttl,
        }
        if existing:
            existing.write(vals)
        else:
            vals["cache_key"] = key
            self.sudo().create(vals)
        return data

    @api.model
    def invalidate_all(self):
        self.sudo().search([]).write({"is_valid": False})
        self.sudo().search([("is_valid", "=", False)]).unlink()

    @api.model
    def cron_refresh_cache(self):
        dashboard = self.env["buz.sales.analytics.dashboard"]
        default_filters = dashboard._get_default_filters()
        key = self._make_key(default_filters)
        data = dashboard._compute_dashboard_data(default_filters)
        self.set_cached(key, data, ttl=60)
        prev_filters = dashboard._get_previous_period_filters()
        if prev_filters:
            prev_key = self._make_key(prev_filters)
            prev_data = dashboard._compute_dashboard_data(prev_filters)
            self.set_cached(prev_key, prev_data, ttl=60)
        self.sudo().search(
            [("is_valid", "=", False), ("cache_key", "!=", key)]
        ).unlink()
