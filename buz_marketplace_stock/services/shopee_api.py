# -*- coding: utf-8 -*-

import hashlib
import hmac
import json
import logging
import time
from datetime import datetime

from odoo import _

from .api_client import BaseAPIClient

_logger = logging.getLogger(__name__)


class ShopeeAPI(BaseAPIClient):
    BASE_URL = 'https://partner.shopeemobile.com'
    BASE_URL_SG = 'https://partner.test.shopeemobile.com'  # staging

    def __init__(self, account):
        super().__init__(account.env)
        self.account = account
        self.partner_id = int(account.shopee_partner_id) if account.shopee_partner_id else 0
        self.partner_key = account.shopee_partner_key or ''
        self.access_token = account.shopee_access_token or ''
        self.shop_id = int(account.shopee_shop_id) if account.shopee_shop_id else 0

    def _get_base_url(self):
        return self.BASE_URL

    def _sign_request(self, path, timestamp):
        base_string = '%s%s%s' % (self.partner_id, path, timestamp)
        sign = hmac.new(
            self.partner_key.encode('utf-8'),
            base_string.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest()
        return sign

    def _call(self, path, body=None, method='POST'):
        timestamp = int(time.time())
        sign = self._sign_request(path, timestamp)
        url = '%s%s' % (self._get_base_url(), path)
        headers = {
            'Content-Type': 'application/json',
        }
        if body is None:
            body = {}
        full_body = {
            'partner_id': self.partner_id,
            'timestamp': timestamp,
            'sign': sign,
            'access_token': self.access_token,
            'shop_id': self.shop_id,
        }
        if isinstance(body, dict):
            full_body.update(body)
        status_code, response, error = self.call(
            self.account, method, url, headers=headers, body=full_body)
        if status_code >= 400:
            _logger.error('Shopee API error: %s - %s', path, error)
            return None
        if response and response.get('error'):
            _logger.error('Shopee API error: %s - %s', path, response.get('message'))
            if response.get('error') == 'error_auth_expired_access_token':
                self.account.action_refresh_token()
            return None
        return response

    def get_shop_info(self):
        path = '/api/v2/shop/get_shop_info'
        return self._call(path)

    def get_items(self, offset=0, limit=100):
        path = '/api/v2/product/get_item_list'
        body = {
            'offset': offset,
            'limit': min(limit, 100),
        }
        return self._call(path, body)

    def get_item_detail(self, item_ids):
        path = '/api/v2/product/get_item_detail'
        body = {
            'item_id_list': item_ids if isinstance(item_ids, list) else [item_ids],
        }
        return self._call(path, body)

    def update_stock(self, item_id, stock_list):
        path = '/api/v2/product/update_stock'
        body = {
            'item_id': item_id,
            'stock_list': [
                {'model_id': model_id, 'stock': stock_qty}
                for model_id, stock_qty in stock_list
            ],
        }
        return self._call(path, body)

    def get_orders(self, order_status_list=None, create_time_from=None, create_time_to=None):
        path = '/api/v2/order/get_order_list'
        body = {
            'time_unit': 'create',
            'page_size': 100,
        }
        if order_status_list:
            body['order_status'] = order_status_list
        if create_time_from:
            body['create_time_from'] = create_time_from
        if create_time_to:
            body['create_time_to'] = create_time_to
        return self._call(path, body)

    def get_order_detail(self, order_sn):
        path = '/api/v2/order/get_order_detail'
        body = {
            'order_sn': order_sn,
        }
        return self._call(path, body)

    def refresh_token(self):
        path = '/api/v2/auth/access_token/get'
        timestamp = int(time.time())
        sign = self._sign_request(path, timestamp)
        url = '%s%s' % (self._get_base_url(), path)
        body = {
            'partner_id': self.partner_id,
            'timestamp': timestamp,
            'sign': sign,
            'refresh_token': self.account.shopee_refresh_token,
        }
        status_code, response, error = self.call(
            self.account, 'POST', url, body=body)
        if status_code < 400 and response and not response.get('error'):
            self.account.write({
                'shopee_access_token': response.get('access_token'),
                'shopee_refresh_token': response.get('refresh_token'),
                'shopee_token_expiry': datetime.fromtimestamp(
                    response.get('expire_in', 0) + time.time()),
            })
            self.access_token = response.get('access_token')
            return True
        _logger.error('Shopee token refresh failed: %s', error or response)
        return False
