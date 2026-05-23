# -*- coding: utf-8 -*-
"""Controllers for report downloads."""

import os

from odoo import http
from odoo.http import request, content_disposition


class ReportDownloadController(http.Controller):

    @http.route('/stock_fifo_by_location/download_report', type='http', auth='user')
    def download_report(self, filepath='', filename='', **kwargs):
        """Download a generated report file."""
        if not filepath or not filename:
            return request.not_found()

        # Security: only allow /tmp/ files
        if not filepath.startswith('/tmp/'):
            return request.not_found()

        if not os.path.exists(filepath):
            return request.not_found()

        with open(filepath, 'rb') as f:
            data = f.read()

        headers = [
            ('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
            ('Content-Disposition', content_disposition(filename)),
            ('Content-Length', len(data)),
        ]
        return request.make_response(data, headers)
