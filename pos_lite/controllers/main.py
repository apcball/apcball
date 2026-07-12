# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request
from odoo.exceptions import UserError, ValidationError, MissingError, AccessError

# Exception types safe to surface to the API client as a normal error response.
# Anything else is a programming error and should propagate as HTTP 500.
_HANDLED_EXCEPTIONS = (UserError, ValidationError, MissingError, AccessError)

# Field whitelists for controller-built O2M commands — defend against field
# injection from the terminal client (no state/company_id/is_return/etc.).
_ORDER_LINE_FIELDS = ('product_id', 'description', 'qty', 'price_unit', 'discount', 'discount_type')


def _sanitize_o2m_payload(raw, allowed_fields):
    """Convert a list of dicts (or [0,0,{...}] commands) into whitelist-only
    create commands. Drops any key not in allowed_fields."""
    commands = []
    if not isinstance(raw, list):
        return commands
    for item in raw:
        vals = None
        if isinstance(item, dict):
            vals = item
        elif isinstance(item, (list, tuple)) and len(item) == 3 and item[0] == 0 and isinstance(item[2], dict):
            vals = item[2]
        if not vals:
            continue
        clean = {k: v for k, v in vals.items() if k in allowed_fields}
        if clean.get('product_id') or clean.get('payment_method'):
            commands.append(fields.Command.create(clean))
    return commands


class PosLiteController(http.Controller):

    # ─── Helpers ────────────────────────────────────────────────

    def _get_json_data(self):
        """Extract JSON-RPC params from the request body (Odoo 17).

        Odoo 17 removed `request.jsonrequest`; the parsed body is available via
        `request.get_json_data()` and the RPC params also land in
        `request.params`. Support both plain-dict and JSON-RPC envelopes.
        """
        data = {}
        try:
            data = request.get_json_data()
        except Exception:
            data = {}
        if isinstance(data, dict) and isinstance(data.get('params'), dict):
            data = data['params']
        if not isinstance(data, dict):
            data = {}
        # Merge dispatcher params (covers odoo.jsonRpc-style clients)
        params = getattr(request, 'params', None)
        if isinstance(params, dict):
            data = {**params, **data}
        return data

    def _get_company_id(self):
        """Current user's active company ID."""
        return request.env.company.id

    def _check_order_access(self, order_id):
        """Browse order as the current user so record rules (employee/session
        restriction in security.xml) apply. Missing or inaccessible → 404-style."""
        try:
            order = request.env['pos.lite.order'].browse(int(order_id))
        except (ValueError, TypeError):
            raise ValidationError('Order not found')
        if not order.exists():
            raise ValidationError('Order not found')
        return order

    # ─── Terminal UI Page ───────────────────────────────────────

    @http.route('/pos_lite/ui', type='http', auth='user')
    def pos_lite_ui(self, **kwargs):
        session_id = kwargs.get('session_id')
        try:
            session_id = int(session_id) if session_id else False
        except (ValueError, TypeError):
            session_id = False
        if not session_id:
            # No session in the URL — fall back to the user's open session so
            # the terminal can be bookmarked directly at /pos_lite/ui.
            session = request.env['pos.lite.session'].search([
                ('state', '=', 'opened'),
                ('company_id', '=', request.env.company.id),
            ], order='id desc', limit=1)
            session_id = session.id or False
        response = request.render('pos_lite.pos_lite_terminal', {
            'session_id': session_id,
        })
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    # ─── Session Info ───────────────────────────────────────────

    @http.route('/pos_lite/api/session_info', type='json', auth='user', methods=['POST'], csrf=False)
    def session_info(self, **kwargs):
        try:
            data = self._get_json_data()
            session_id = data.get('session_id')
            result = {
                'employees': [],
                'default_warehouse_id': False,
                'default_warehouse_name': '',
                'default_pricelist_id': False,
                'default_pricelist_name': '',
            }
            if session_id:
                session = request.env['pos.lite.session'].sudo().browse(int(session_id))
                if session.exists() and session.company_id.id in request.env.companies.ids:
                    result['session_name'] = session.name
                    result['session_state'] = session.state
                    # Only show employees assigned to this session
                    employees = session.employee_ids | session.employee_id
                    if employees:
                        result['employees'] = [{'id': e.id, 'name': e.name} for e in employees]
                    if session.config_id.warehouse_id:
                        w = session.config_id.warehouse_id
                        result['default_warehouse_id'] = w.id
                        result['default_warehouse_name'] = w.name
                    if session.config_id.pricelist_id:
                        p = session.config_id.pricelist_id
                        result['default_pricelist_id'] = p.id
                        result['default_pricelist_name'] = p.name
                    if session.config_id.default_trade_channel:
                        result['default_trade_channel'] = session.config_id.default_trade_channel
                    else:
                        result['default_trade_channel'] = session.current_trade_channel or False
                    # Trade channel options for the terminal dropdown — the
                    # dynamic selection lives on pos.lite.order itself.
                    fg = request.env['pos.lite.order'].fields_get(['trade_channel'])
                    selection = fg.get('trade_channel', {}).get('selection') or []
                    result['trade_channel_options'] = [
                        {'key': k, 'value': v} for k, v in selection
                    ]
            # No session_id → no employees (terminal requires a session to start)
            return {'success': True, **result}
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Warehouses ─────────────────────────────────────────────

    @http.route('/pos_lite/api/warehouses', type='json', auth='user', methods=['POST'], csrf=False)
    def get_warehouses(self, **kwargs):
        try:
            warehouses = request.env['stock.warehouse'].search_read(
                [('company_id', '=', self._get_company_id())],
                ['name', 'code'],
                order='name',
            )
            return {'success': True, 'warehouses': warehouses}
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Products ───────────────────────────────────────────────

    @http.route('/pos_lite/api/products', type='json', auth='user', methods=['POST'], csrf=False)
    def get_products(self, **kwargs):
        try:
            data = self._get_json_data()
            session_id = data.get('session_id')
            warehouse_id = data.get('warehouse_id')
            warehouse = False
            cid = self._get_company_id()

            if warehouse_id:
                warehouse = request.env['stock.warehouse'].sudo().search([
                    ('id', '=', int(warehouse_id)),
                    ('company_id', '=', cid),
                ], limit=1)
            elif session_id:
                session = request.env['pos.lite.session'].sudo().browse(int(session_id))
                if session.exists() and session.company_id.id in request.env.companies.ids:
                    if session.config_id.warehouse_id:
                        warehouse = session.config_id.warehouse_id
            if not warehouse:
                config = request.env['pos.lite.config'].get_default_config()
                if config and config.warehouse_id:
                    warehouse = config.warehouse_id
            if not warehouse:
                warehouse = request.env['stock.warehouse'].search([
                    ('company_id', '=', cid),
                ], limit=1)

            location = warehouse.lot_stock_id if warehouse else False

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
                # Pre-fetch tax rates for all products
                tax_ids_set = set()
                for p in products:
                    for tid in (p.get('taxes_id') or []):
                        tax_ids_set.add(tid)
                tax_rate_map = {}
                if tax_ids_set:
                    for tax in request.env['account.tax'].sudo().browse(tax_ids_set):
                        tax_rate_map[tax.id] = tax.amount
                for p in products:
                    p['qty_available'] = qty_map.get(p['id'], 0.0)
                    # Compute effective tax rate for this product
                    tax_rate = 0.0
                    for tid in (p.get('taxes_id') or []):
                        tax_rate += tax_rate_map.get(tid, 0.0)
                    p['tax_rate'] = tax_rate
                    if p.get('image_128'):
                        p['image_128'] = p['image_128'].decode() if isinstance(p['image_128'], bytes) else p['image_128']
                    if p.get('image_256'):
                        p['image_256'] = p['image_256'].decode() if isinstance(p['image_256'], bytes) else p['image_256']
            else:
                products = []

            return {'success': True, 'products': products}
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Create Order (whitelisted fields only) ─────────────────

    @http.route('/pos_lite/api/create_order', type='json', auth='user', methods=['POST'], csrf=False)
    def create_order(self, **kwargs):
        try:
            data = self._get_json_data()
            cid = self._get_company_id()

            # Resolve warehouse & pricelist from session/config
            wh_id = data.get('warehouse_id')
            session_id = data.get('session_id')
            employee_id = data.get('employee_id')
            pricelist_id = False

            if session_id:
                session = request.env['pos.lite.session'].sudo().browse(int(session_id))
                if session.exists() and session.company_id.id in request.env.companies.ids:
                    wh_id = wh_id or session.config_id.warehouse_id.id
                    pricelist_id = session.config_id.pricelist_id.id

            if not wh_id or not pricelist_id:
                config = request.env['pos.lite.config'].get_default_config()
                if config:
                    wh_id = wh_id or config.warehouse_id.id
                    pricelist_id = pricelist_id or (config.pricelist_id and config.pricelist_id.id)
            if not pricelist_id:
                pricelist = request.env['product.pricelist'].search([
                    '|', ('company_id', '=', False), ('company_id', '=', cid),
                ], limit=1)
                if pricelist:
                    pricelist_id = pricelist.id

            # Optional pre-selected partner (created via create_customer);
            # validated against the active company before it is trusted.
            partner_id = False
            raw_partner_id = data.get('partner_id')
            if raw_partner_id:
                try:
                    partner = request.env['res.partner'].sudo().browse(int(raw_partner_id))
                except (ValueError, TypeError):
                    raise ValidationError('Invalid partner')
                if not partner.exists() or partner.company_id.id not in (False, cid):
                    raise ValidationError('Invalid partner')
                partner_id = partner.id

            # Whitelisted vals only — no state, company_id, is_return injection
            order_vals = {
                'company_id': cid,
                'partner_id': partner_id,
                'customer_name': data.get('customer_name', ''),
                'partner_phone': data.get('partner_phone', ''),
                'partner_address': data.get('partner_address', ''),
                'channel': data.get('channel', 'walkin'),
                'trade_channel': data.get('trade_channel'),
                'note': data.get('note', ''),
                'warehouse_id': wh_id,
                'pricelist_id': pricelist_id,
                'session_id': int(session_id) if session_id else False,
                'employee_id': int(employee_id) if employee_id else False,
                'line_ids': _sanitize_o2m_payload(data.get('line_ids'), _ORDER_LINE_FIELDS),
            }

            order = request.env['pos.lite.order'].create(order_vals)
            order.action_process_order()
            return {'success': True, 'order_id': order.id, 'name': order.name}
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Create Customer ────────────────────────────────────────

    @http.route('/pos_lite/api/create_customer', type='json', auth='user', methods=['POST'], csrf=False)
    def create_customer(self, **kwargs):
        """Create a customer with full tax-invoice details from the terminal.

        Runs as sudo: cashiers (group_pos_lite_user) are not partner managers,
        same reasoning as the sudo partner creation in
        pos.lite.order._get_or_create_customer_partner. Input is whitelisted
        field-by-field below — nothing from the payload is passed through raw.
        """
        try:
            data = self._get_json_data()
            cid = self._get_company_id()
            partner = request.env['res.partner'].sudo().pos_lite_create_customer(data, cid)
            address = ' '.join(filter(None, [
                partner.street, partner.city, partner.zip]))
            return {
                'success': True,
                'partner': {
                    'id': partner.id,
                    'name': partner.name,
                    'phone': partner.phone or '',
                    'address': address,
                },
            }
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Order Detail ───────────────────────────────────────────

    @http.route('/pos_lite/api/order_detail', type='json', auth='user', methods=['POST'], csrf=False)
    def order_detail(self, **kwargs):
        try:
            data = self._get_json_data()
            order_id = data.get('order_id')
            if not order_id:
                return {'success': False, 'error': 'order_id required'}
            order = self._check_order_access(order_id)

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
                    'id': line.id,
                    'product_id': line.product_id.id,
                    'product_name': line.product_id.display_name,
                    'default_code': line.product_id.default_code or '',
                    'qty': line.qty,
                    'price_unit': line.price_unit,
                    'discount': line.discount,
                    'price_total': line.price_total,
                    'returned_qty': line.returned_qty,
                    'available_return_qty': line.available_return_qty,
                })
            for pay in order.payment_ids:
                order_data['payments'].append({
                    'payment_method': pay.payment_method,
                    'amount': pay.amount,
                    'reference': pay.reference or '',
                })
            return {'success': True, 'order': order_data}
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Orders For Return ──────────────────────────────────────

    @http.route('/pos_lite/api/orders_for_return', type='json', auth='user', methods=['POST'], csrf=False)
    def orders_for_return(self, **kwargs):
        try:
            data = self._get_json_data()
            limit = data.get('limit', 50)
            orders = request.env['pos.lite.order'].search([
                ('state', '=', 'done'),
                ('is_return', '=', False),
                ('company_id', '=', self._get_company_id()),
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
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Create Return (with qty validation) ────────────────────

    @http.route('/pos_lite/api/create_return', type='json', auth='user', methods=['POST'], csrf=False)
    def create_return(self, **kwargs):
        try:
            data = self._get_json_data()
            if not isinstance(data, dict):
                return {'success': False, 'error': 'Invalid data'}
            original_order_id = data.get('original_order_id')
            lines = data.get('lines', [])
            if not original_order_id or not lines:
                return {'success': False, 'error': 'original_order_id and lines required'}

            original = self._check_order_access(original_order_id)
            if original.state != 'done':
                return {'success': False, 'error': 'Only completed orders can be returned'}

            # Validate return qty against available_return_qty and remember the
            # original line so returned_from_line_id links the return back
            # (otherwise available_return_qty never decreases for API returns).
            matched_lines = []
            for line_data in lines:
                product_id = line_data.get('product_id')
                return_qty = line_data.get('qty', 1)
                orig_line = original.line_ids.filtered(lambda l: l.product_id.id == product_id)
                if not orig_line:
                    return {'success': False, 'error': 'Product %s not found in original order' % product_id}
                available = orig_line[0].available_return_qty
                if return_qty <= 0:
                    return {'success': False, 'error': 'Return qty must be positive'}
                if return_qty > available:
                    return {'success': False, 'error': 'Return qty for %s exceeds available (%s > %s)' % (
                        orig_line[0].product_id.display_name, return_qty, available)}
                matched_lines.append(orig_line[0])

            return_vals = {
                'company_id': original.company_id.id,
                'customer_name': original.customer_name,
                'partner_phone': original.partner_phone,
                'partner_address': original.partner_address,
                'channel': original.channel,
                'trade_channel': original.trade_channel,
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

            for line_data, orig_line in zip(lines, matched_lines):
                # Refund at the effective (discounted) price actually paid,
                # matching the backend return wizard behaviour.
                refund_price = (
                    orig_line.price_subtotal / orig_line.qty
                    if orig_line.qty else line_data.get('price_unit', 0)
                )
                return_vals['line_ids'].append([0, 0, {
                    'returned_from_line_id': orig_line.id,
                    'product_id': line_data.get('product_id'),
                    'qty': line_data.get('qty', 1),
                    'price_unit': refund_price,
                    'discount': 0,
                    'discount_type': 'fixed',
                }])

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

            return_vals.pop('payment_ids', None)
            order = request.env['pos.lite.order'].create(return_vals)
            # Refund amount computed server-side from the created order — the
            # client-provided figure may not include taxes/discounts correctly.
            request.env['pos.lite.payment'].create({
                'order_id': order.id,
                'payment_method': data.get('payment_method', 'cash'),
                'amount': -abs(order.amount_total),
                'reference': data.get('reference', ''),
                'note': data.get('reason', '') or 'Customer return refund',
            })
            order.action_process_order()
            return {'success': True, 'order_id': order.id, 'name': order.name}
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}

    # ─── Product Search ─────────────────────────────────────────

    @http.route('/pos_lite/api/product_search', type='json', auth='user', methods=['POST'], csrf=False)
    def product_search(self, **kwargs):
        try:
            data = self._get_json_data()
            term = data.get('term', '')
            products = request.env['product.product'].sudo().search([
                '|', '|',
                ('name', 'ilike', term),
                ('default_code', 'ilike', term),
                ('barcode', 'ilike', term),
                ('sale_ok', '=', True),
                ('can_be_pos', '=', True),
                '|', ('company_id', '=', False), ('company_id', '=', self._get_company_id()),
            ], limit=20)
            # Batch qty_available via read_group on stock.quant instead of
            # touching p.qty_available per product (N+1 on big catalogs).
            qty_map = {}
            if products:
                quants = request.env['stock.quant'].read_group(
                    domain=[('product_id', 'in', products.ids),
                            ('location_id.usage', '=', 'internal')],
                    fields=['product_id', 'quantity:sum'],
                    groupby=['product_id'],
                    lazy=False,
                )
                for q in quants:
                    pid = q['product_id'][0] if isinstance(q['product_id'], (list, tuple)) else q['product_id']
                    qty_map[pid] = qty_map.get(pid, 0.0) + q['quantity']
            result = []
            for p in products:
                result.append({
                    'id': p.id,
                    'name': p.display_name,
                    'default_code': p.default_code or '',
                    'list_price': p.list_price,
                    'qty_available': qty_map.get(p.id, 0.0),
                })
            return {'success': True, 'products': result}
        except _HANDLED_EXCEPTIONS as e:
            return {'success': False, 'error': str(e)}
