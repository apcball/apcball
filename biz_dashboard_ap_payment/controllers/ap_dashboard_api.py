# -*- coding: utf-8 -*-
from odoo import http
from odoo.exceptions import AccessError
from odoo.http import content_disposition, request

from ..models.ap_dashboard import SHEETS

XLSX_MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'


class ApDashboardAPI(http.Controller):
    """Thin HTTP layer; all logic lives in the ``biz.ap.dashboard`` engine."""

    @staticmethod
    def _filters(month, year, company_id, project_id, partner_id):
        return {
            'month': month,
            'year': year,
            'company_id': company_id,
            'project_id': project_id,
            'partner_id': partner_id,
        }

    @http.route('/ap_dashboard/api/data', type='json', auth='user')
    def get_data(self, month=None, year=None, company_id=None, project_id=None,
                 partner_id=None, refresh=False, **kwargs):
        return request.env['biz.ap.dashboard'].get_dashboard_data(
            self._filters(month, year, company_id, project_id, partner_id),
            refresh=bool(refresh))

    @http.route('/ap_dashboard/api/export', type='http', auth='user')
    def export(self, month=None, year=None, company_id=None, project_id=None,
               partner_id=None, sheet='all', **kwargs):
        if sheet not in SHEETS:
            return request.make_response('Invalid sheet', status=400)
        filters = self._filters(month, year, company_id, project_id, partner_id)
        engine = request.env['biz.ap.dashboard']
        try:
            content = engine.build_export(filters, sheet)
            f = engine._normalize_filters(filters)
        except AccessError:
            return request.make_response('Access denied', status=403)
        filename = 'ap_payment_dashboard_%04d-%02d_%s.xlsx' % (f['year'], f['month'], sheet)
        return request.make_response(content, headers=[
            ('Content-Type', XLSX_MIME),
            ('Content-Disposition', content_disposition(filename)),
        ])
