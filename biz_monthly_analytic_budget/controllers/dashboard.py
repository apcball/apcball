# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class BudgetDashboardController(http.Controller):

    @http.route('/budget/dashboard/plans', type='json', auth='user')
    def get_available_plans(self, company_id=None):
        return request.env['monthly.budget.report'].get_available_plans(company_id=company_id)

    @http.route('/budget/dashboard/data', type='json', auth='user')
    def get_dashboard_data(self, filters=None):
        if filters is None:
            filters = {}
        return request.env['monthly.budget.report'].get_dashboard_data(filters)
