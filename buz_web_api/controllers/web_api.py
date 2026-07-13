from odoo import http
from odoo.http import request


class WebApiController(http.Controller):
    @http.route('/web_api/v1/health', type='http', auth='public', methods=['GET'], csrf=False)
    def health(self, **kwargs):
        login = request.httprequest.headers.get('X-Odoo-Login')
        api_key = request.httprequest.headers.get('X-Odoo-API-Key')
        if not login or not api_key:
            return request.make_json_response(
                {'ok': False, 'error': 'X-Odoo-Login and X-Odoo-API-Key are required.'},
                status=401,
            )

        user_id = request.env['res.users.apikeys'].sudo()._check_credentials(
            scope='rpc',
            key=api_key,
        )
        user = request.env['res.users'].sudo().browse(user_id).exists() if user_id else False
        if not user or user.login != login:
            return request.make_json_response(
                {'ok': False, 'error': 'Invalid Odoo API credentials.'},
                status=401,
            )

        return request.make_json_response({
            'ok': True,
            'uid': user.id,
            'database': request.db,
        })
