# -*- coding: utf-8 -*-
import json
from odoo import http
from odoo.http import request

class PosLiteController(http.Controller):

    @http.route('/pos_lite/ui', type='http', auth='user')
    def pos_lite_ui(self, **kwargs):
        return request.render('pos_lite.pos_lite_terminal', {})

    @http.route('/pos_lite/api/products', type='json', auth='user', methods=['POST'])
    def get_products(self, **kwargs):
        products = request.env['product.product'].search_read(
            [('sale_ok', '=', True)],
            ['name', 'list_price', 'default_code', 'categ_id', 'barcode', 'taxes_id']
        )
        return {'success': True, 'products': products}

    @http.route('/pos_lite/api/create_order', type='json', auth='user', methods=['POST'])
    def create_order(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
            order = request.env['pos.lite.order'].create(data)
            return {'success': True, 'order_id': order.id, 'name': order.name}
        except Exception as e:
            return {'success': False, 'error': str(e)}