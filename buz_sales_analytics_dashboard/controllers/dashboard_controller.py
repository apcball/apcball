from odoo import http
from odoo.http import request


class SalesAnalyticsDashboardController(http.Controller):

    @http.route("/sales/analytics/dashboard/data", type="json", auth="user")
    def get_dashboard_data(self, filters=None):
        if filters is None:
            filters = {}
        return request.env[
            "buz.sales.analytics.dashboard"
        ].get_dashboard_data(filters)

    @http.route("/sales/analytics/dashboard/refresh", type="json", auth="user")
    def refresh_dashboard_data(self, filters=None):
        if filters is None:
            filters = {}
        request.env["buz.sales.analytics.cache"].invalidate_all()
        return request.env[
            "buz.sales.analytics.dashboard"
        ].get_dashboard_data(filters)

    @http.route("/sales/analytics/dashboard/filter_options", type="json", auth="user")
    def get_filter_options(self):
        return request.env[
            "buz.sales.analytics.dashboard"
        ].get_filter_options()
