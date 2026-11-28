import json

from werkzeug.exceptions import BadRequest, Forbidden

from odoo import fields, http
from odoo.exceptions import AccessError, UserError
from odoo.http import content_disposition, request

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class SalesDashboardController(http.Controller):

    @http.route("/buz_sales_dashboard/target_template", type="http", auth="user",
                methods=["GET"])
    def target_template(self, **kwargs):
        try:
            content = request.env["buz.sales.target.import"]._template_xlsx()
        except (AccessError, UserError):
            raise Forbidden()
        return request.make_response(content, headers=[
            ("Content-Type", XLSX),
            ("Content-Disposition", content_disposition("sales_target_template.xlsx")),
            ("Content-Length", len(content)),
        ])

    @http.route("/buz_sales_dashboard/export", type="http", auth="user",
                methods=["POST"])
    def export(self, filters="{}", **kwargs):
        report = request.env["buz.sales.dashboard.report"]
        try:
            values = json.loads(filters)
        except ValueError:
            raise BadRequest("filters must be JSON")
        # runs as the logged-in user: access rights and record rules apply
        content = report._export_xlsx(values)
        filename = "Sales_Dashboard_%s.xlsx" % fields.Date.context_today(report)
        return request.make_response(content, headers=[
            ("Content-Type", XLSX),
            ("Content-Disposition", content_disposition(filename)),
            ("Content-Length", len(content)),
        ])
