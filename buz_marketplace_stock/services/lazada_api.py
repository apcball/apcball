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


class LazadaAPI(BaseAPIClient):
    BASE_URL = 'https://api.lazada.com.my/rest'
    BASE_URL_TH = 'https://api.lazada.co.th/rest'
    BASE_URL_SG = 'https://api.lazada.sg/rest'

    def __init__(self, account):
        super().__init__(account.env)
        self.account = account
        self.app_key = account.lazada_app_key or ''
        self.app_secret = account.lazada_app_secret or ''
        self.access_token = account.lazada_access_token or ''
        self.country_code = account.lazada_country_code or 'TH'

    def _get_base_url(self):
        country_urls = {
            'TH': self.BASE_URL_TH,
            'SG': self.BASE_URL_SG,
            'MY': self.BASE_URL,
        }
        return country_urls.get(self.country_code, self.BASE_URL_TH)

    def _sign_request(self, parameters):
        keys = sorted(parameters.keys())
        base_string = ''
        for key in keys:
            base_string += '%s%s' % (key, parameters[key])
        base_string = self.app_secret + base_string + self.app_secret
        sign = hmac.new(
            self.app_secret.encode('utf-8'),
            base_string.encode('utf-8'),
            hashlib.sha256,
        ).hexdigest().upper()
        return sign

    def _call(self, path, parameters=None, method='POST'):
        if parameters is None:
            parameters = {}
        timestamp = int(time.time() * 1000)
        parameters.update({
            'app_key': self.app_key,
            'timestamp': timestamp,
            'access_token': self.access_token,
        })
        sign = self._sign_request(parameters)
        parameters['sign'] = sign
        url = '%s%s' % (self._get_base_url(), path)
        headers = {
            'Content-Type': 'application/json',
        }
        if method == 'GET':
            status_code, response, error = self.call(
                self.account, 'GET', url, headers=headers, body=parameters)
        else:
            url_params = '&'.join(
                '%s=%s' % (k, v) for k, v in sorted(parameters.items()))
            full_url = '%s?%s' % (url, url_params)
            status_code, response, error = self.call(
                self.account, 'POST', full_url, headers=headers)
        if status_code >= 400:
            _logger.error('Lazada API error: %s - %s', path, error)
            return None
        if response and response.get('code') and response.get('code') != '0':
            _logger.error('Lazada API error: %s - %s', path, response.get('message'))
            return None
        if response and 'data' in response:
            return response['data']
        return response

    def get_products(self, offset=0, limit=100, filter='all'):
        path = '/products/get'
        parameters = {
            'filter': filter,
            'offset': offset,
            'limit': limit,
        }
        result = self._call(path, parameters, method='GET')
        if result and 'products' in result:
            return result['products']
        return []

    def get_orders(self, created_after=None, status=None):
        path = '/orders/get'
        parameters = {
            'created_after': created_after or datetime.now().isoformat(),
            'sort_by': 'created_at',
            'sort_direction': 'DESC',
        }
        if status:
            parameters['status'] = status
        result = self._call(path, parameters, method='GET')
        if result and 'orders' in result:
            return result['orders']
        return []

    def update_stock(self, seller_sku, stock_qty):
        path = '/product/stock/update'
        parameters = {
            'seller_sku': seller_sku,
            'stock': stock_qty,
        }
        return self._call(path, parameters, method='POST')
