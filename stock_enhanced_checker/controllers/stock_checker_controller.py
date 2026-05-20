# -*- coding: utf-8 -*-
# File: controllers/stock_checker_controller.py
# Purpose: JSON-RPC HTTP controller providing stock data endpoints
#          consumed by the Stock Enhanced Checker OWL frontend.

import json
import logging
from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class StockCheckerController(http.Controller):
    """
    HTTP JSON controller for the Stock Enhanced Checker dashboard.
    All endpoints are POST JSON and require user authentication.
    """

    @http.route('/stock_checker/warehouses', type='json', auth='user', methods=['POST'])
    def get_warehouses(self):
        """
        Return all active warehouses.

        :return: list of warehouse dicts
        """
        helper = request.env['stock.checker.helper']
        return helper.get_warehouses()

    @http.route('/stock_checker/locations', type='json', auth='user', methods=['POST'])
    def get_locations(self, warehouse_id=None):
        """
        Return internal locations for the given warehouse.

        :param warehouse_id: int
        :return: list of location dicts
        """
        helper = request.env['stock.checker.helper']
        return helper.get_locations(warehouse_id)

    @http.route('/stock_checker/stock_data', type='json', auth='user', methods=['POST'])
    def get_stock_data(self, location_id=None, search='', filter_type='all',
                       offset=0, limit=50):
        """
        Return paginated stock data for products at the given location.

        :param location_id: int
        :param search: str, search term
        :param filter_type: str
        :param offset: int
        :param limit: int
        :return: dict with 'products' and 'total'
        """
        helper = request.env['stock.checker.helper']
        return helper.get_stock_data(
            location_id=location_id,
            search=search,
            filter_type=filter_type,
            offset=offset,
            limit=limit,
        )

    @http.route('/stock_checker/create_quotation', type='json', auth='user', methods=['POST'])
    def create_quotation(self, lines=None, partner_id=None, partner_name=None):
        """
        Create a Sale Order quotation from selected product lines.

        :param lines: list of {'product_id': int, 'qty': float, 'price': float}
        :param partner_id: int or None — existing partner ID
        :param partner_name: str or None — name for a new partner
        :return: dict with 'sale_order_id' and 'name'
        """
        if lines is None:
            lines = []
        helper = request.env['stock.checker.helper']
        return helper.create_quotation(
            lines,
            partner_id=partner_id,
            partner_name=partner_name,
        )

    @http.route('/stock_checker/user_rights', type='json', auth='user', methods=['POST'])
    def get_user_rights(self):
        """
        Return the current user's stock checker permissions.

        :return: dict with 'can_create_quotation'
        """
        helper = request.env['stock.checker.helper']
        return helper.get_user_rights()

    @http.route('/stock_checker/preferences', type='json', auth='user', methods=['POST'])
    def get_preferences(self):
        """
        Return stored warehouse/location preferences for the current user.

        :return: dict with 'warehouse_id' and 'location_id'
        """
        helper = request.env['stock.checker.helper']
        return helper.get_user_preferences()

    @http.route('/stock_checker/save_preferences', type='json', auth='user', methods=['POST'])
    def save_preferences(self, warehouse_id=None, location_id=None):
        """
        Persist warehouse/location preferences for the current user.

        :param warehouse_id: int
        :param location_id: int
        :return: bool
        """
        helper = request.env['stock.checker.helper']
        return helper.save_user_preferences(warehouse_id, location_id)
