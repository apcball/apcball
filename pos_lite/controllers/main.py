# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request

class PosLiteController(http.Controller):

    @http.route('/pos_lite/ui', type='http', auth='user')
    def pos_lite_ui(self, **kwargs):
        session_id = kwargs.get('session_id')
        return request.render('pos_lite.pos_lite_terminal', {
            'session_id': session_id and int(session_id) or False,
        })

    @http.route('/pos_lite/api/session_info', type='json', auth='user', methods=['POST'], csrf=False)
    def session_info(self, **kwargs):
        try:
            data = request.jsonrequest if hasattr(request, 'jsonrequest') else kwargs
            session_id = data.get('session_id') if isinstance(data, dict) else None
            result = {
                'employees': [],
                'default_warehouse_id': False,
                'default_warehouse_name': '',
                'default_pricelist_id': False,
                'default_pricelist_name': '',
            }
            if session_id:
                session = request.env['pos.lite.session'].sudo().browse(int(session_id))
                if session.exists():
                    # Employees from employee_ids
                    employees = session.employee_ids or session.employee_id
                    if employees:
                        emp_data = []
                        for e in employees:
                            emp_data.append({
                                'id': e.id,
                                'name': e.name,
                            })
                        result['employees'] = emp_data
                    # Default warehouse from config
                    if session.config_id.warehouse_id:
                        w = session.config_id.warehouse_id
                        result['default_warehouse_id'] = w.id
                        result['default_warehouse_name'] = w.name
                    # Default pricelist from config
                    if session.config_id.pricelist_id:
                        p = session.config_id.pricelist_id
                        result['default_pricelist_id'] = p.id
                        result['default_pricelist_name'] = p.name
            if not result['employees']:
                # Fallback: all employees of current user's company
                employees = request.env['hr.employee'].search([
                    ('company_id', '=', request.env.company.id),
                ], limit=50)
                result['employees'] = [{'id': e.id, 'name': e.name} for e in employees]
            return {'success': True, **result}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/pos_lite/api/warehouses', type='json', auth='user', methods=['POST'], csrf=False)
    def get_warehouses(self, **kwargs):
        try:
            warehouses = request.env['stock.warehouse'].search_read(
                [],
                ['name', 'code', 'company_id'],
                order='name',
            )
            return {'success': True, 'warehouses': warehouses}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/pos_lite/api/products', type='json', auth='user', methods=['POST'], csrf=False)
    def get_products(self, **kwargs):
        try:
            data = request.jsonrequest if hasattr(request, 'jsonrequest') else kwargs
            session_id = data.get('session_id') if isinstance(data, dict) else None
            warehouse_id = data.get('warehouse_id') if isinstance(data, dict) else None
            warehouse = False

            # Priority: explicit warehouse_id > session's warehouse
            if warehouse_id:
                warehouse = request.env['stock.warehouse'].sudo().browse(int(warehouse_id))
            elif session_id:
                session = request.env['pos.lite.session'].sudo().browse(int(session_id))
                if session.exists() and session.config_id.warehouse_id:
                    warehouse = session.config_id.warehouse_id
            if not warehouse:
                config = request.env['pos.lite.config'].get_default_config()
                if config and config.warehouse_id:
                    warehouse = config.warehouse_id
            if not warehouse:
                warehouse = request.env['stock.warehouse'].search([], limit=1)

            location = warehouse.lot_stock_id if warehouse else False

            # Find products that have stock at this warehouse location
            if location:
                quant_data = request.env['stock.quant'].read_group(
                    domain=[('location_id', '=', location.id)],
                    fields=['product_id', 'quantity:sum'],
                    groupby=['product_id'],
                    lazy=False,
                )
                product_ids_in_stock = []
                qty_map = {}
                for q in quant_data:
                    pid = q['product_id'][0] if isinstance(q['product_id'], (list, tuple)) else q['product_id']
                    qty = q['quantity']
                    product_ids_in_stock.append(pid)
                    qty_map[pid] = qty

                products = request.env['product.product'].search_read(
                    [
                        ('id', 'in', product_ids_in_stock),
                        ('sale_ok', '=', True),
                        ('can_be_pos', '=', True),
                    ],
                    ['name', 'list_price', 'default_code', 'categ_id', 'barcode',
                     'taxes_id', 'image_128', 'image_256']
                )
                for p in products:
                    p['qty_available'] = qty_map.get(p['id'], 0.0)
                    # Convert binary fields to base64 strings for JSON serialization
                    if p.get('image_128'):
                        p['image_128'] = p['image_128'].decode() if isinstance(p['image_128'], bytes) else p['image_128']
                    if p.get('image_256'):
                        p['image_256'] = p['image_256'].decode() if isinstance(p['image_256'], bytes) else p['image_256']
            else:
                products = []
                qty_map = {}

            return {'success': True, 'products': products}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/pos_lite/api/create_order', type='json', auth='user', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        try:
            data = request.jsonrequest if hasattr(request, 'jsonrequest') else kwargs
            if not isinstance(data, dict):
                data = {}
            # Fetch warehouse from data or session config
            wh_id = data.get('warehouse_id')
            session_id = data.get('session_id')
            employee_id = data.get('employee_id')
            pricelist_id = False
            if session_id:
                session = request.env['pos.lite.session'].sudo().browse(int(session_id))
                if session.exists() and session.config_id.warehouse_id:
                    wh_id = wh_id or session.config_id.warehouse_id.id
                    pricelist_id = session.config_id.pricelist_id.id
            if not wh_id or not pricelist_id:
                config = request.env['pos.lite.config'].get_default_config()
                if config:
                    wh_id = wh_id or config.warehouse_id.id
                    if config.pricelist_id:
                        pricelist_id = pricelist_id or config.pricelist_id.id
            if not pricelist_id:
                pricelist = request.env['product.pricelist'].search([], limit=1)
                if pricelist:
                    pricelist_id = pricelist.id
            if wh_id:
                data['warehouse_id'] = wh_id
            if pricelist_id:
                data['pricelist_id'] = pricelist_id
            if employee_id:
                data['employee_id'] = int(employee_id)
            order = request.env['pos.lite.order'].create(data)
            # Process order (create invoice + picking)
            result = order.action_quick_pay_and_process()
            return {'success': True, 'order_id': order.id, 'name': order.name}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/pos_lite/api/order_detail', type='json', auth='user', methods=['POST'], csrf=False)
    def order_detail(self, **kwargs):
        try:
            data = request.jsonrequest if hasattr(request, 'jsonrequest') else kwargs
            order_id = data.get('order_id') if isinstance(data, dict) else None
            if not order_id:
                return {'success': False, 'error': 'order_id required'}
            order = request.env['pos.lite.order'].sudo().browse(int(order_id))
            if not order.exists():
                return {'success': False, 'error': 'Order not found'}

            base_url = request.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
            order_data = {
                'id': order.id,
                'name': order.name,
                'customer_name': order.customer_name,
                'partner_phone': order.partner_phone,
                'date_order': order.date_order.isoformat() if order.date_order else None,
                'state': order.state,
                'employee_name': order.employee_id.name if order.employee_id else '',
                'amount_untaxed': order.amount_untaxed,
                'amount_tax': order.amount_tax,
                'amount_total': order.amount_total,
                'amount_paid': order.amount_paid,
                'amount_change': order.amount_change,
                'is_return': order.is_return,
                'is_exchange': order.is_exchange,
                'lines': [],
                'payments': [],
                'print_urls': {
                    'receipt_58mm': '%s/report/pdf/pos_lite.action_report_pos_lite_receipt_58mm/%s' % (base_url, order.id),
                    'receipt_80mm': '%s/report/pdf/pos_lite.action_report_pos_lite_receipt_80mm/%s' % (base_url, order.id),
                    'receipt_a4': '%s/report/pdf/pos_lite.action_report_pos_lite_receipt_a4/%s' % (base_url, order.id),
                    'invoice': '%s/report/pdf/pos_lite.action_report_pos_lite_invoice/%s' % (base_url, order.id) if order.invoice_id else None,
                },
            }
            for line in order.line_ids:
                order_data['lines'].append({
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name,
                    'default_code': line.product_id.default_code or '',
                    'qty': line.qty,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'price_total': line.price_total,
                })
            for pay in order.payment_ids:
                order_data['payments'].append({
                    'payment_method': pay.payment_method,
                    'amount': pay.amount,
                    'reference': pay.reference or '',
                })
            return {'success': True, 'order': order_data}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/pos_lite/api/orders_for_return', type='json', auth='user', methods=['POST'], csrf=False)
    def orders_for_return(self, **kwargs):
        try:
            data = request.jsonrequest if hasattr(request, 'jsonrequest') else kwargs
            limit = data.get('limit', 50) if isinstance(data, dict) else 50
            orders = request.env['pos.lite.order'].sudo().search([
                ('state', '=', 'done'),
                ('is_return', '=', False),
            ], order='date_order desc', limit=int(limit))
            result = []
            for o in orders:
                result.append({
                    'id': o.id,
                    'name': o.name,
                    'customer_name': o.customer_name or '',
                    'date_order': o.date_order.isoformat() if o.date_order else None,
                    'amount_total': o.amount_total,
                    'employee_name': o.employee_id.name if o.employee_id else '',
                })
            return {'success': True, 'orders': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/pos_lite/api/create_return', type='json', auth='user', methods=['POST'], csrf=False)
    def create_return(self, **kwargs):
        try:
            data = request.jsonrequest if hasattr(request, 'jsonrequest') else kwargs
            if not isinstance(data, dict):
                return {'success': False, 'error': 'Invalid data'}
            original_order_id = data.get('original_order_id')
            lines = data.get('lines', [])
            if not original_order_id or not lines:
                return {'success': False, 'error': 'original_order_id and lines required'}

            original = request.env['pos.lite.order'].sudo().browse(int(original_order_id))
            if not original.exists():
                return {'success': False, 'error': 'Original order not found'}

            return_vals = {
                'customer_name': original.customer_name,
                'partner_phone': original.partner_phone,
                'partner_address': original.partner_address,
                'channel': original.channel,
                'session_id': data.get('session_id') or original.session_id.id,
                'employee_id': data.get('employee_id') or original.employee_id.id,
                'warehouse_id': original.warehouse_id.id or data.get('warehouse_id'),
                'pricelist_id': original.pricelist_id.id,
                'is_return': True,
                'is_exchange': data.get('is_exchange', False),
                'return_of_order_id': original.id,
                'return_reason': data.get('reason', ''),
                'line_ids': [],
                'payment_ids': [],
            }

            for line_data in lines:
                return_vals['line_ids'].append([0, 0, {
                    'product_id': line_data.get('product_id'),
                    'qty': line_data.get('qty', 1),
                    'price_unit': line_data.get('price_unit', 0),
                    'discount': 0,
                    'discount_type': 'fixed',
                }])

            # If exchange, add new (exchange) lines
            exchange_lines = data.get('exchange_lines', [])
            if exchange_lines:
                return_vals['is_exchange'] = True
                for el in exchange_lines:
                    return_vals['line_ids'].append([0, 0, {
                        'product_id': el.get('product_id'),
                        'qty': el.get('qty', 1),
                        'price_unit': el.get('price_unit', 0),
                        'discount': 0,
                        'discount_type': 'fixed',
                    }])

            # Payment for return (negative)
            return_vals['payment_ids'].append([0, 0, {
                'payment_method': data.get('payment_method', 'cash'),
                'amount': data.get('amount', 0),
                'reference': data.get('reference', ''),
                'state': 'paid',
            }])

            order = request.env['pos.lite.order'].create(return_vals)
            result = order.action_quick_pay_and_process()
            return {'success': True, 'order_id': order.id, 'name': order.name}
        except Exception as e:
            return {'success': False, 'error': str(e)}

    @http.route('/pos_lite/api/product_search', type='json', auth='user', methods=['POST'], csrf=False)
    def product_search(self, **kwargs):
        try:
            data = request.jsonrequest if hasattr(request, 'jsonrequest') else kwargs
            term = data.get('term', '') if isinstance(data, dict) else ''
            products = request.env['product.product'].sudo().search([
                '|', '|',
                ('name', 'ilike', term),
                ('default_code', 'ilike', term),
                ('barcode', 'ilike', term),
                ('sale_ok', '=', True),
                ('can_be_pos', '=', True),
            ], limit=20)
            result = []
            for p in products:
                result.append({
                    'id': p.id,
                    'name': p.display_name,
                    'default_code': p.default_code or '',
                    'list_price': p.list_price,
                    'qty_available': p.qty_available,
                })
            return {'success': True, 'products': result}
        except Exception as e:
            return {'success': False, 'error': str(e)}