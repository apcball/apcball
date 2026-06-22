from odoo import http
from odoo.http import request


class WarrantyDashboardController(http.Controller):

    @http.route("/warranty/dashboard/data", type="json", auth="user")
    def get_dashboard_data(self, filters=None):
        if filters is None:
            filters = {}
        return request.env["warranty.dashboard"].get_dashboard_data(filters)

    @http.route("/warranty/dashboard/refresh", type="json", auth="user")
    def refresh_dashboard_data(self, filters=None):
        if filters is None:
            filters = {}
        return request.env["warranty.dashboard"].refresh_dashboard_data(filters)

    @http.route("/warranty/dashboard/rebuild", type="json", auth="user")
    def rebuild_cache(self):
        return request.env["warranty.dashboard"].rebuild_cache()

    @http.route("/warranty/dashboard/filter_options", type="json", auth="user")
    def get_filter_options(self):
        return request.env["warranty.dashboard"].get_filter_options()
