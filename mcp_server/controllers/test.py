# -*- coding: utf-8 -*-

from odoo import http
from odoo.http import request


class TestController(http.Controller):
    @http.route('/test/ping', type='http', auth='none', methods=['GET'], csrf=False)
    def test_ping(self, **kwargs):
        return request.make_json_response({'status': 'ok'})
