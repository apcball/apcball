# -*- coding: utf-8 -*-
# File: models/stock_checker.py
# Purpose: Core helper model providing all stock data computation methods
#          used by the Stock Enhanced Checker OWL dashboard.

import logging
from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class StockCheckerHelper(models.TransientModel):
    """
    Transient helper model for the Stock Enhanced Checker dashboard.
    Exposes RPC-callable methods that aggregate stock, reservation,
    and incoming quantities per product/location.
    """
    _name = 'stock.checker.helper'
    _description = 'Stock Checker Helper'

    @api.model
    def get_warehouses(self):
        warehouses = self.env['stock.warehouse'].search([('active', '=', True)])
        return [
            {
                'id': wh.id,
                'name': wh.name,
                'lot_stock_id': wh.lot_stock_id.id if wh.lot_stock_id else False,
            }
            for wh in warehouses
        ]

    @api.model
    def get_locations(self, warehouse_id):
        if not warehouse_id:
            return []
        warehouse = self.env['stock.warehouse'].browse(warehouse_id)
        if not warehouse.exists():
            return []
        parent_location = warehouse.lot_stock_id
        locations = self.env['stock.location'].search([
            ('id', 'child_of', parent_location.id),
            ('usage', '=', 'internal'),
            ('active', '=', True),
        ])
        return [
            {'id': loc.id, 'name': loc.name, 'complete_name': loc.complete_name}
            for loc in locations
        ]

    @api.model
    def get_pricelists(self):
        """
        Return all active sale pricelists for the pricelist selector.

        :return: list of {'id': int, 'name': str, 'currency': str}
        """
        pricelists = self.env['product.pricelist'].search([
            ('active', '=', True),
        ])
        return [
            {
                'id': pl.id,
                'name': pl.name,
                'currency': pl.currency_id.name if pl.currency_id else '',
            }
            for pl in pricelists
        ]

    @api.model
    def get_stock_data(self, location_id, search='', filter_type='all',
                       offset=0, limit=50, pricelist_id=False):
        """
        Fetch paginated product stock data for the given location.
        When pricelist_id is provided, prices are computed via that pricelist.

        Performance optimizations vs previous version:
          - PO incoming: use read_group instead of Python loop
          - Reorder points: single read_group
          - Product read: only fetch needed fields via read()
          - Pricelist: batch _get_products_price() instead of per-product loop
        """
        if not location_id:
            return {'products': [], 'total': 0, 'stats': {}}

        location = self.env['stock.location'].browse(location_id)
        if not location.exists():
            return {'products': [], 'total': 0, 'stats': {}}

        low_stock_threshold = int(
            self.env['ir.config_parameter'].sudo().get_param(
                'stock_enhanced_checker.low_stock_threshold', '5'
            )
        )

        # Get all child locations (inclusive)
        child_location_ids = self.env['stock.location'].search([
            ('id', 'child_of', location_id),
            ('usage', '=', 'internal'),
            ('active', '=', True),
        ]).ids
        if not child_location_ids:
            child_location_ids = [location_id]

        # ── 1. On-hand quantities ────────────────────────────────────────
        quants = self.env['stock.quant'].read_group(
            [('location_id', 'in', child_location_ids), ('quantity', '>', 0)],
            ['product_id', 'quantity:sum'],
            ['product_id'],
        )
        qty_on_hand_map = {q['product_id'][0]: q['quantity'] for q in quants}

        # ── 2. Reserved quantities ───────────────────────────────────────
        reserved_lines = self.env['stock.move.line'].read_group(
            [
                ('location_id', 'in', child_location_ids),
                ('state', 'in', ('partially_available', 'assigned')),
                ('quantity', '>', 0),
            ],
            ['product_id', 'quantity:sum'],
            ['product_id'],
        )
        qty_reserved_map = {r['product_id'][0]: r['quantity'] for r in reserved_lines}

        # ── 3. Incoming from confirmed POs — optimized via read_group ────
        po_rg = self.env['purchase.order.line'].read_group(
            [('order_id.state', '=', 'purchase'), ('product_qty', '>', 0)],
            ['product_id', 'product_qty:sum', 'qty_received:sum'],
            ['product_id'],
        )
        incoming_map = {}
        for grp in po_rg:
            pending = (grp.get('product_qty') or 0) - (grp.get('qty_received') or 0)
            if pending > 0 and grp['product_id']:
                incoming_map[grp['product_id'][0]] = pending

        # PO refs: still needs a search but only for products with incoming
        po_refs_map = {}
        if incoming_map:
            incoming_product_ids = list(incoming_map.keys())
            po_line_refs = self.env['purchase.order.line'].search_read(
                [
                    ('order_id.state', '=', 'purchase'),
                    ('product_id', 'in', incoming_product_ids),
                ],
                ['product_id', 'order_id'],
            )
            for line in po_line_refs:
                pid = line['product_id'][0]
                po_name = line['order_id'][1]
                if pid not in po_refs_map:
                    po_refs_map[pid] = set()
                po_refs_map[pid].add(po_name)
            # Convert sets to comma-separated strings
            po_refs_map = {k: ', '.join(sorted(v)) for k, v in po_refs_map.items()}

        # ── 4. Reorder points — optimized via read_group ─────────────────
        orderpoint_rg = self.env['stock.warehouse.orderpoint'].read_group(
            [('location_id', 'in', child_location_ids)],
            ['product_id', 'product_min_qty:min'],
            ['product_id'],
        )
        reorder_map = {o['product_id'][0]: o['product_min_qty'] for o in orderpoint_rg if o['product_id']}

        # ── 5. Build product pool — only fetch needed fields ─────────────
        product_domain = [
            ('active', '=', True),
            ('type', '=', 'product'),
        ]
        if search:
            product_domain = ['&'] + product_domain + [
                '|', ('name', 'ilike', search), ('default_code', 'ilike', search),
            ]

        # Use search + read to only fetch fields we need
        product_records = self.env['product.product'].search(product_domain)
        products_data = product_records.read([
            'id', 'display_name', 'default_code', 'uom_id', 'list_price', 'taxes_id',
        ]) if product_records else []

        # ── 5b. Batch pricelist price computation ────────────────────────
        pricelist_prices = {}
        if pricelist_id and products_data:
            try:
                Pricelist = self.env['product.pricelist'].browse(pricelist_id)
                if Pricelist.exists():
                    # _get_products_price returns {product_id: price}
                    pricelist_prices = Pricelist._get_products_price(
                        product_records, 1.0
                    )
            except Exception:
                _logger.debug('stock_enhanced_checker: pricelist price computation failed', exc_info=True)

        # ── 5c. Batch tax computation for VAT-inclusive prices ───────────
        tax_cache = {}
        vat_price_map = {}
        tax_computation_base = {}  # {product_id: base_price}
        tax_product_map = {}  # {tax_id: [product_ids]}

        for prod_data in products_data:
            pid = prod_data['id']
            base_price = pricelist_prices.get(pid, prod_data.get('list_price', 0))
            tax_computation_base[pid] = base_price
            tax_ids = prod_data.get('taxes_id', [])
            for tid in tax_ids:
                tax_product_map.setdefault(tid, []).append(pid)

        if tax_product_map:
            for tax_id, pids in tax_product_map.items():
                if tax_id not in tax_cache:
                    tax = self.env['account.tax'].browse(tax_id)
                    if tax.exists():
                        tax_cache[tax_id] = tax

            for pid, base_price in tax_computation_base.items():
                prod_data = next((p for p in products_data if p['id'] == pid), None)
                if not prod_data:
                    continue
                tax_ids = prod_data.get('taxes_id', [])
                if tax_ids:
                    taxes = self.env['account.tax'].browse(tax_ids)
                    try:
                        tax_result = taxes.compute_all(base_price)
                        vat_price_map[pid] = tax_result['total_included']
                    except Exception:
                        vat_price_map[pid] = base_price

        # ── 6. Apply filter and build result ─────────────────────────────
        result = []
        full_stats = {'in_stock': 0, 'low_stock': 0, 'out_of_stock': 0, 'with_incoming': 0}

        uom_cache = {}

        for prod_data in products_data:
            pid = prod_data['id']
            on_hand = qty_on_hand_map.get(pid, 0.0)
            reserved = qty_reserved_map.get(pid, 0.0)
            actual_available = on_hand - reserved
            incoming = incoming_map.get(pid, 0.0)
            reorder_point = reorder_map.get(pid, 0.0)

            if actual_available > low_stock_threshold:
                full_stats['in_stock'] += 1
            elif actual_available > 0:
                full_stats['low_stock'] += 1
            else:
                full_stats['out_of_stock'] += 1
            if incoming > 0:
                full_stats['with_incoming'] += 1

            if filter_type == 'in_stock' and actual_available <= 0:
                continue
            if filter_type == 'out_of_stock' and actual_available > 0:
                continue
            if filter_type == 'low_stock' and not (0 < actual_available <= low_stock_threshold):
                continue

            # Get uom name from cache
            uom_id = prod_data.get('uom_id')
            if uom_id and uom_id[0] not in uom_cache:
                uom_cache[uom_id[0]] = uom_id[1]
            uom_name = uom_cache.get(uom_id[0], '') if uom_id else ''

            # Price: pricelist price if available, else list_price — VAT inclusive
            base_price = pricelist_prices.get(pid, prod_data.get('list_price', 0))
            list_price = vat_price_map.get(pid, base_price)

            result.append({
                'id': pid,
                'name': prod_data.get('display_name', ''),
                'default_code': prod_data.get('default_code') or '',
                'uom_name': uom_name,
                'qty_on_hand': round(on_hand, 3),
                'qty_reserved': round(reserved, 3),
                'actual_available': round(actual_available, 3),
                'incoming_qty': round(incoming, 3),
                'po_refs': po_refs_map.get(pid, ''),
                'reorder_point': round(reorder_point, 3),
                'list_price': round(list_price, 2),
                'tax_ids': prod_data.get('taxes_id', []),
                'low_stock_threshold': low_stock_threshold,
            })

        result.sort(key=lambda x: (x['actual_available'] >= 0, x['name']))

        total = len(result)
        paginated = result[offset: offset + limit]
        return {
            'products': paginated,
            'total': total,
            'stats': full_stats,
        }

    @api.model
    def search_partner(self, query, limit=10):
        if not query or not query.strip():
            return []
        domain = [
            '|',
            ('partner_code', 'ilike', query.strip()),
            ('name', 'ilike', query.strip()),
        ]
        partners = self.env['res.partner'].search(domain, limit=limit)
        return [
            {
                'id': p.id,
                'name': p.name,
                'ref': p.partner_code or '',
                'display': f'[{p.partner_code}] {p.name}' if p.partner_code else p.name,
            }
            for p in partners
        ]

    @api.model
    def create_quotation(self, lines, partner_id=None, partner_name=None,
                         pricelist_id=None):
        """
        Create a Sale Order (quotation) with the given product lines and partner.
        Optionally applies a pricelist to the sale order.

        :param lines: list of {'product_id': int, 'qty': float, 'price': float}
        :param partner_id: int or None
        :param partner_name: str or None
        :param pricelist_id: int or None — pricelist to apply on the SO
        """
        if not lines:
            return {'error': 'No products selected'}

        try:
            SaleOrder = self.env['sale.order']
            SaleOrderLine = self.env['sale.order.line']
            Partner = self.env['res.partner']

            # ── Resolve partner ──
            if partner_id:
                partner = Partner.browse(int(partner_id))
                if not partner.exists():
                    _logger.warning('stock_enhanced_checker: partner_id=%s not found', partner_id)
                    partner_id = self.env.user.partner_id.id
                else:
                    partner_id = partner.id
            elif partner_name and partner_name.strip():
                new_partner = Partner.create({'name': partner_name.strip()})
                partner_id = new_partner.id
                _logger.info('stock_enhanced_checker: created new partner "%s" id=%s',
                             partner_name.strip(), partner_id)
            else:
                partner_id = self.env.user.partner_id.id

            # ── Create Sale Order ──
            order_vals = {'partner_id': partner_id}

            # Apply pricelist if provided
            if pricelist_id:
                pricelist = self.env['product.pricelist'].browse(int(pricelist_id))
                if pricelist.exists():
                    order_vals['pricelist_id'] = pricelist.id

            order = SaleOrder.create(order_vals)

            for line in lines:
                product = self.env['product.product'].browse(line.get('product_id'))
                if not product.exists():
                    _logger.warning('stock_enhanced_checker: skipping unknown product_id=%s',
                                    line.get('product_id'))
                    continue

                SaleOrderLine.create({
                    'order_id': order.id,
                    'product_id': product.id,
                    'product_uom_qty': float(line.get('qty', 1.0)),
                    'price_unit': float(line.get('price', product.list_price)),
                    'product_uom': product.uom_id.id,
                })

            return {
                'sale_order_id': order.id,
                'name': order.name,
            }

        except Exception as exc:
            _logger.exception('stock_enhanced_checker: create_quotation failed')
            return {'error': str(exc)}

    @api.model
    def get_user_rights(self):
        can_create = self.env.user.has_group(
            'stock_enhanced_checker.group_stock_checker_quotation'
        )
        return {'can_create_quotation': can_create}

    @api.model
    def get_user_preferences(self):
        uid = str(self.env.uid)
        ICP = self.env['ir.config_parameter'].sudo()
        param_wh = ICP.get_param(f'stock_enhanced_checker.user_{uid}_warehouse_id')
        param_loc = ICP.get_param(f'stock_enhanced_checker.user_{uid}_location_id')
        param_pl = ICP.get_param(f'stock_enhanced_checker.user_{uid}_pricelist_id')
        return {
            'warehouse_id': int(param_wh) if param_wh else False,
            'location_id': int(param_loc) if param_loc else False,
            'pricelist_id': int(param_pl) if param_pl else False,
        }

    @api.model
    def save_user_preferences(self, warehouse_id, location_id, pricelist_id=False):
        uid = str(self.env.uid)
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param(f'stock_enhanced_checker.user_{uid}_warehouse_id',
                      str(warehouse_id) if warehouse_id else '')
        ICP.set_param(f'stock_enhanced_checker.user_{uid}_location_id',
                      str(location_id) if location_id else '')
        ICP.set_param(f'stock_enhanced_checker.user_{uid}_pricelist_id',
                      str(pricelist_id) if pricelist_id else '')
        return True
