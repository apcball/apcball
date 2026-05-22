# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request, Response
import json

class PosLiteController(http.Controller):

    @http.route('/pos_lite/ui', type='http', auth='user')
    def pos_lite_ui(self, **kwargs):
        session_id = kwargs.get('session_id')
        return request.render('pos_lite.pos_lite_terminal', {
            'session_id': session_id and int(session_id) or False,
        })

    @http.route('/pos_lite/api/products', type='http', auth='user', methods=['POST'], csrf=False)
    def get_products(self, **kwargs):
        products = request.env['product.product'].search_read(
            [('sale_ok', '=', True), ('can_be_pos', '=', True)],
            ['name', 'list_price', 'default_code', 'categ_id', 'barcode', 'taxes_id']
        )
        return Response(json.dumps({'success': True, 'products': products}), content_type='application/json')

    @http.route('/pos_lite/api/create_order', type='http', auth='user', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
            order = request.env['pos.lite.order'].create(data)
            return Response(json.dumps({'success': True, 'order_id': order.id, 'name': order.name}), content_type='application/json')
        except Exception as e:
            return Response(json.dumps({'success': False, 'error': str(e)}), content_type='application/json')