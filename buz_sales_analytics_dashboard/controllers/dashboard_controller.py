from odoo import http
from odoo.exceptions import AccessError
from odoo.http import request


class SalesAnalyticsDashboardController(http.Controller):

    def _check_access(self):
        if not request.env.user.has_group(
            "buz_sales_analytics_dashboard.group_sales_analytics_user"
        ):
            raise AccessError("You are not allowed to access sales analytics data.")

    @http.route("/sales/analytics/dashboard/data", type="json", auth="user")
    def get_dashboard_data(self, filters=None):
        self._check_access()
        if filters is None:
            filters = {}
        return request.env[
            "buz.sales.analytics.dashboard"
        ].get_dashboard_data(filters)

    @http.route("/sales/analytics/dashboard/refresh", type="json", auth="user")
    def refresh_dashboard_data(self, filters=None):
        self._check_access()
        if filters is None:
            filters = {}
        return request.env[
            "buz.sales.analytics.dashboard"
        ].refresh_dashboard_data(filters)

    @http.route("/sales/analytics/dashboard/filter_options", type="json", auth="user")
    def get_filter_options(self):
        self._check_access()
        return request.env[
            "buz.sales.analytics.dashboard"
        ].get_filter_options()
