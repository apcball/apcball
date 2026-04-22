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
        """
        Return all active warehouses as a list of dicts.

        :return: list of {'id': int, 'name': str, 'lot_stock_id': int}
        """
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
        """
        Return all internal locations that are children of the given warehouse's
        main stock location.

        :param warehouse_id: int, ID of the stock.warehouse record
        :return: list of {'id': int, 'name': str, 'complete_name': str}
        """
        if not warehouse_id:
            return []

        warehouse = self.env['stock.warehouse'].browse(warehouse_id)
        if not warehouse.exists():
            return []

        parent_location = warehouse.lot_stock_id
        # Search for all internal child locations (recursive via child_of)
        locations = self.env['stock.location'].search([
            ('id', 'child_of', parent_location.id),
            ('usage', '=', 'internal'),
            ('active', '=', True),
        ])
        return [
            {
                'id': loc.id,
                'name': loc.name,
                'complete_name': loc.complete_name,
            }
            for loc in locations
        ]

    @api.model
    def get_stock_data(self, location_id, search='', filter_type='all', offset=0, limit=50):
        """
        Fetch paginated product stock data for the given location.

        Quantities computed:
          - qty_on_hand: sum of stock.quant.quantity at location
          - qty_reserved: sum of reserved_qty from outgoing stock.move.line at location
          - actual_available: qty_on_hand - qty_reserved
          - incoming_qty: sum of (product_qty - qty_received) from confirmed PO lines

        :param location_id: int, ID of stock.location
        :param search: str, search term for product name or internal reference
        :param filter_type: str, one of 'all', 'in_stock', 'out_of_stock', 'low_stock'
        :param offset: int, pagination offset
        :param limit: int, number of records per page
        :return: dict with 'products' list and 'total' count
        """
        if not location_id:
            return {'products': [], 'total': 0}

        location = self.env['stock.location'].browse(location_id)
        if not location.exists():
            return {'products': [], 'total': 0}

        # Get low stock threshold from config
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

        # ── 1. On-hand quantities from stock.quant ──────────────────────────
        quant_domain = [
            ('location_id', 'in', child_location_ids),
            ('quantity', '>', 0),
        ]
        quants = self.env['stock.quant'].read_group(
            quant_domain,
            fields=['product_id', 'quantity:sum'],
            groupby=['product_id'],
        )
        qty_on_hand_map = {q['product_id'][0]: q['quantity'] for q in quants}

        # ── 2. Reserved quantities from outgoing stock.move.line ────────────
        reserved_domain = [
            ('location_id', 'in', child_location_ids),
            ('state', 'in', ('partially_available', 'assigned')),
            ('quantity', '>', 0),
        ]
        reserved_lines = self.env['stock.move.line'].read_group(
            reserved_domain,
            fields=['product_id', 'quantity:sum'],
            groupby=['product_id'],
        )
        qty_reserved_map = {r['product_id'][0]: r['quantity'] for r in reserved_lines}

        # ── 3. Incoming from confirmed Purchase Orders ──────────────────────
        # Search all confirmed PO lines; filter in Python for qty_received < product_qty
        po_lines = self.env['purchase.order.line'].search([
            ('order_id.state', '=', 'purchase'),
        ])
        incoming_map = {}
        po_refs_map = {}
        for line in po_lines:
            if line.qty_received < line.product_qty:
                pid = line.product_id.id
                pending = line.product_qty - line.qty_received
                incoming_map[pid] = incoming_map.get(pid, 0.0) + pending
                po_name = line.order_id.name
                if pid not in po_refs_map:
                    po_refs_map[pid] = []
                if po_name not in po_refs_map[pid]:
                    po_refs_map[pid].append(po_name)

        # ── 4. Reorder points ───────────────────────────────────────────────
        orderpoints = self.env['stock.warehouse.orderpoint'].search([
            ('location_id', 'in', child_location_ids),
        ])
        reorder_map = {}
        for op in orderpoints:
            pid = op.product_id.id
            if pid not in reorder_map:
                reorder_map[pid] = op.product_min_qty

        # ── 5. Build product pool ───────────────────────────────────────────
        all_product_ids = set(qty_on_hand_map.keys())

        # Build product domain for search
        product_domain = [
            ('id', 'in', list(all_product_ids)),
            ('active', '=', True),
        ]
        if search:
            product_domain += ['|',
                ('name', 'ilike', search),
                ('default_code', 'ilike', search),
            ]

        products = self.env['product.product'].search(product_domain)

        # ── 6. Apply filter ─────────────────────────────────────────────────
        result = []
        for prod in products:
            pid = prod.id
            on_hand = qty_on_hand_map.get(pid, 0.0)
            reserved = qty_reserved_map.get(pid, 0.0)
            actual_available = on_hand - reserved
            incoming = incoming_map.get(pid, 0.0)
            reorder_point = reorder_map.get(pid, 0.0)

            # Apply filter_type
            if filter_type == 'in_stock' and actual_available <= 0:
                continue
            if filter_type == 'out_of_stock' and actual_available > 0:
                continue
            if filter_type == 'low_stock' and not (0 < actual_available <= low_stock_threshold):
                continue

            result.append({
                'id': pid,
                'name': prod.display_name,
                'default_code': prod.default_code or '',
                'uom_name': prod.uom_id.name if prod.uom_id else '',
                'qty_on_hand': round(on_hand, 3),
                'qty_reserved': round(reserved, 3),
                'actual_available': round(actual_available, 3),
                'incoming_qty': round(incoming, 3),
                'po_refs': ', '.join(po_refs_map.get(pid, [])),
                'reorder_point': round(reorder_point, 3),
                'list_price': prod.list_price,
                'low_stock_threshold': low_stock_threshold,
            })

        # Sort: negative available first, then by name
        result.sort(key=lambda x: (x['actual_available'] >= 0, x['name']))

        total = len(result)
        paginated = result[offset: offset + limit]
        return {'products': paginated, 'total': total}

    @api.model
    def search_partner(self, query, limit=10):
        """
        Search partners by partner_code (from buz_partner_code_auto) or name.
        Used by the partner code autocomplete in the Stock Checker dashboard.

        :param query: str, search term
        :param limit: int, max results
        :return: list of {'id', 'name', 'partner_code', 'display'}
        """
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
                'ref': p.partner_code or '',       # send as 'ref' so frontend stays unchanged
                'display': f'[{p.partner_code}] {p.name}' if p.partner_code else p.name,
            }
            for p in partners
        ]

    @api.model
    def create_quotation(self, lines, partner_id=None, partner_name=None):
        """
        Create a Sale Order (quotation) with the given product lines and partner.

        Partner resolution order:
          1. partner_id provided → use existing partner
          2. partner_name provided (no partner_id) → create new res.partner
          3. Neither → fallback to current user's partner

        :param lines: list of {'product_id': int, 'qty': float, 'price': float}
        :param partner_id: int or None — existing partner ID
        :param partner_name: str or None — name for a new partner
        :return: dict with 'sale_order_id' and 'name', or 'error' key on failure
        """
        if not lines:
            return {'error': 'No products selected'}

        try:
            SaleOrder = self.env['sale.order']
            SaleOrderLine = self.env['sale.order.line']
            Partner = self.env['res.partner']

            # ── Resolve partner ──────────────────────────────────────────
            if partner_id:
                partner = Partner.browse(int(partner_id))
                if not partner.exists():
                    _logger.warning(
                        'stock_enhanced_checker: partner_id=%s not found, falling back',
                        partner_id,
                    )
                    partner_id = self.env.user.partner_id.id
                else:
                    partner_id = partner.id
            elif partner_name and partner_name.strip():
                # Create new partner on-the-fly
                new_partner = Partner.create({'name': partner_name.strip()})
                partner_id = new_partner.id
                _logger.info(
                    'stock_enhanced_checker: created new partner "%s" id=%s',
                    partner_name.strip(), partner_id,
                )
            else:
                # Fallback: current user's partner
                partner_id = self.env.user.partner_id.id

            # ── Create Sale Order ────────────────────────────────────────
            order = SaleOrder.create({
                'partner_id': partner_id,
            })

            for line in lines:
                product = self.env['product.product'].browse(line.get('product_id'))
                if not product.exists():
                    _logger.warning(
                        'stock_enhanced_checker: skipping unknown product_id=%s',
                        line.get('product_id'),
                    )
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
    def get_user_preferences(self):
        """
        Return stored warehouse/location preferences for the current user.

        :return: dict with 'warehouse_id' and 'location_id'
        """
        uid = str(self.env.uid)
        param_wh = self.env['ir.config_parameter'].sudo().get_param(
            f'stock_enhanced_checker.user_{uid}_warehouse_id'
        )
        param_loc = self.env['ir.config_parameter'].sudo().get_param(
            f'stock_enhanced_checker.user_{uid}_location_id'
        )
        return {
            'warehouse_id': int(param_wh) if param_wh else False,
            'location_id': int(param_loc) if param_loc else False,
        }

    @api.model
    def save_user_preferences(self, warehouse_id, location_id):
        """
        Persist warehouse/location selection for the current user.

        :param warehouse_id: int
        :param location_id: int
        :return: bool True on success
        """
        uid = str(self.env.uid)
        ICP = self.env['ir.config_parameter'].sudo()
        if warehouse_id:
            ICP.set_param(f'stock_enhanced_checker.user_{uid}_warehouse_id', str(warehouse_id))
        if location_id:
            ICP.set_param(f'stock_enhanced_checker.user_{uid}_location_id', str(location_id))
        return True
