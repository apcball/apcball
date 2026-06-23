# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class MarketplaceAccount(models.Model):
    _name = 'buz.marketplace.account'
    _description = 'Marketplace Account'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(
        string='Account Name',
        required=True,
        tracking=True
    )
    platform = fields.Selection([
        ('shopee', 'Shopee'),
        ('lazada', 'Lazada'),
    ], string='Platform', required=True, tracking=True)
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    buffer_location_id = fields.Many2one(
        'stock.location',
        string='Buffer Location',
        domain="[('usage', '=', 'internal'), ('company_id', '=', company_id)]",
        check_company=True,
        tracking=True
    )
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        string='Warehouse',
        check_company=True,
        tracking=True
    )
    product_category_id = fields.Many2one(
        'product.category',
        string='Default Product Category'
    )

    # Shopee fields
    shopee_partner_id = fields.Char(
        string='Shopee Partner ID'
    )
    shopee_partner_key = fields.Char(
        string='Shopee Partner Key'
    )
    shopee_redirect_uri = fields.Char(
        string='Shopee Redirect URI',
        default='https://your-odoo-domain.com/marketplace/shopee/auth'
    )
    shopee_access_token = fields.Char(
        string='Shopee Access Token'
    )
    shopee_refresh_token = fields.Char(
        string='Shopee Refresh Token'
    )
    shopee_token_expiry = fields.Datetime(
        string='Shopee Token Expiry'
    )
    shopee_shop_id = fields.Char(
        string='Shopee Shop ID'
    )

    # Lazada fields
    lazada_app_key = fields.Char(
        string='Lazada App Key'
    )
    lazada_app_secret = fields.Char(
        string='Lazada App Secret'
    )
    lazada_access_token = fields.Char(
        string='Lazada Access Token'
    )
    lazada_token_expiry = fields.Datetime(
        string='Lazada Token Expiry'
    )
    lazada_country_code = fields.Selection([
        ('TH', 'Thailand'),
        ('SG', 'Singapore'),
        ('MY', 'Malaysia'),
        ('PH', 'Philippines'),
        ('ID', 'Indonesia'),
        ('VN', 'Vietnam'),
    ], string='Lazada Country', default='TH')

    # API settings
    api_call_delay = fields.Float(
        string='API Call Delay (seconds)',
        default=1.0,
        help='Delay between API calls to avoid rate limiting'
    )
    api_max_retries = fields.Integer(
        string='Max Retries',
        default=3,
        help='Maximum retry attempts when rate limited'
    )
    order_lookback_minutes = fields.Integer(
        string='Order Lookback (minutes)',
        default=30,
        help='Time window to fetch orders'
    )

    # Computed fields
    product_count = fields.Integer(
        string='Products',
        compute='_compute_product_count'
    )
    order_count = fields.Integer(
        string='Orders',
        compute='_compute_order_count'
    )

    def _compute_product_count(self):
        for account in self:
            account.product_count = self.env['buz.marketplace.product'].search_count([
                ('account_id', '=', account.id)
            ])

    def _compute_order_count(self):
        for account in self:
            account.order_count = self.env['buz.marketplace.order'].search_count([
                ('account_id', '=', account.id)
            ])

    @api.constrains('platform', 'shopee_partner_id', 'lazada_app_key')
    def _check_platform_credentials(self):
        for account in self:
            if account.platform == 'shopee' and not account.shopee_partner_id:
                raise ValidationError(_('Shopee Partner ID is required for Shopee accounts'))
            if account.platform == 'lazada' and not account.lazada_app_key:
                raise ValidationError(_('Lazada App Key is required for Lazada accounts'))

    def action_test_connection(self):
        """Test connection to marketplace API"""
        self.ensure_one()
        
        try:
            if self.platform == 'shopee':
                from ..services.shopee_api import ShopeeAPI
                api = ShopeeAPI(self)
                result = api.get_shop_info()
                if result:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Connection Successful'),
                            'message': _('Successfully connected to Shopee'),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
            elif self.platform == 'lazada':
                from ..services.lazada_api import LazadaAPI
                api = LazadaAPI(self)
                result = api.get_products(limit=1)
                if result:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Connection Successful'),
                            'message': _('Successfully connected to Lazada'),
                            'type': 'success',
                            'sticky': False,
                        }
                    }
            
            raise UserError(_('Connection test failed'))
            
        except Exception as e:
            _logger.error(f'Connection test failed: {str(e)}')
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Connection Failed'),
                    'message': str(e),
                    'type': 'danger',
                    'sticky': True,
                }
            }

    def action_fetch_products(self):
        """Fetch products from marketplace and create/update binding records"""
        self.ensure_one()

        created = 0
        updated = 0
        try:
            if self.platform == 'shopee':
                from ..services.shopee_api import ShopeeAPI
                api = ShopeeAPI(self)
                
                # Get all items with pagination
                offset = 0
                limit = 100
                created = 0
                updated = 0
                
                while True:
                    items_response = api.get_items(offset=offset, limit=limit)
                    if not items_response or 'item' not in items_response:
                        break
                    
                    items = items_response['item']
                    if not items:
                        break
                    
                    # Get item IDs for detail fetch
                    item_ids = [item['item_id'] for item in items]
                    
                    # Get detailed info
                    details_response = api.get_item_detail(item_ids)
                    if not details_response or 'item_list' not in details_response:
                        break
                    
                    for item in details_response['item_list']:
                        result = self._process_shopee_product(item)
                        if result == 'created':
                            created += 1
                        elif result == 'updated':
                            updated += 1
                    
                    if len(items) < limit:
                        break
                    offset += limit
                
                self.message_post(
                    body=_('Fetched Shopee products: %s created, %s updated') % (created, updated)
                )
                
            elif self.platform == 'lazada':
                from ..services.lazada_api import LazadaAPI
                api = LazadaAPI(self)
                
                offset = 0
                limit = 100
                created = 0
                updated = 0
                
                while True:
                    products = api.get_products(offset=offset, limit=limit)
                    if not products:
                        break
                    
                    for product in products:
                        result = self._process_lazada_product(product)
                        if result == 'created':
                            created += 1
                        elif result == 'updated':
                            updated += 1
                    
                    if len(products) < limit:
                        break
                    offset += limit
                
                self.message_post(
                    body=_('Fetched Lazada products: %s created, %s updated') % (created, updated)
                )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Products Fetched'),
                    'message': _('Created: %s, Updated: %s') % (created, updated),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f'Fetch products failed: {str(e)}')
            raise UserError(_('Failed to fetch products: %s') % str(e))

    def _process_shopee_product(self, item):
        """Process a single Shopee product"""
        MarketplaceProduct = self.env['buz.marketplace.product']
        
        item_id = str(item.get('item_id'))
        has_variations = item.get('has_model', False)
        
        if has_variations and 'model' in item:
            # Handle variations
            for model in item['model']:
                model_id = str(model.get('model_id'))
                existing = MarketplaceProduct.search([
                    ('account_id', '=', self.id),
                    ('marketplace_item_id', '=', item_id),
                    ('marketplace_variation_id', '=', model_id),
                ], limit=1)
                
                values = {
                    'account_id': self.id,
                    'marketplace_item_id': item_id,
                    'marketplace_variation_id': model_id,
                    'marketplace_name': f"{item.get('item_name')} - {model.get('model_sku', '')}",
                    'marketplace_sku': model.get('model_sku', ''),
                    'marketplace_price': model.get('price', 0.0),
                    'marketplace_stock': float(model.get('stock_info', [{}])[0].get('stock', 0)),
                    'last_sync_date': fields.Datetime.now(),
                }
                
                if existing:
                    existing.write(values)
                    return 'updated'
                else:
                    MarketplaceProduct.create(values)
                    return 'created'
        else:
            # Single product without variations
            existing = MarketplaceProduct.search([
                ('account_id', '=', self.id),
                ('marketplace_item_id', '=', item_id),
                ('marketplace_variation_id', '=', False),
            ], limit=1)
            
            values = {
                'account_id': self.id,
                'marketplace_item_id': item_id,
                'marketplace_variation_id': False,
                'marketplace_name': item.get('item_name'),
                'marketplace_sku': item.get('item_sku', ''),
                'marketplace_price': item.get('price', 0.0),
                'marketplace_stock': float(item.get('stock_info', [{}])[0].get('stock', 0)),
                'last_sync_date': fields.Datetime.now(),
            }
            
            if existing:
                existing.write(values)
                return 'updated'
            else:
                MarketplaceProduct.create(values)
                return 'created'

    def _process_lazada_product(self, product):
        """Process a single Lazada product"""
        MarketplaceProduct = self.env['buz.marketplace.product']
        
        item_id = str(product.get('item_id'))
        skus = product.get('skus', [])
        
        if len(skus) > 1:
            # Handle variations
            for sku in skus:
                variation_id = str(sku.get('sku_id'))
                existing = MarketplaceProduct.search([
                    ('account_id', '=', self.id),
                    ('marketplace_item_id', '=', item_id),
                    ('marketplace_variation_id', '=', variation_id),
                ], limit=1)
                
                values = {
                    'account_id': self.id,
                    'marketplace_item_id': item_id,
                    'marketplace_variation_id': variation_id,
                    'marketplace_name': f"{product.get('attributes', {}).get('name', '')} - {sku.get('seller_sku', '')}",
                    'marketplace_sku': sku.get('seller_sku', ''),
                    'marketplace_price': float(sku.get('price', 0.0)),
                    'marketplace_stock': float(sku.get('quantity', 0)),
                    'last_sync_date': fields.Datetime.now(),
                }
                
                if existing:
                    existing.write(values)
                    return 'updated'
                else:
                    MarketplaceProduct.create(values)
                    return 'created'
        else:
            # Single product
            sku = skus[0] if skus else {}
            existing = MarketplaceProduct.search([
                ('account_id', '=', self.id),
                ('marketplace_item_id', '=', item_id),
                ('marketplace_variation_id', '=', False),
            ], limit=1)
            
            values = {
                'account_id': self.id,
                'marketplace_item_id': item_id,
                'marketplace_variation_id': False,
                'marketplace_name': product.get('attributes', {}).get('name', ''),
                'marketplace_sku': sku.get('seller_sku', ''),
                'marketplace_price': float(sku.get('price', 0.0)),
                'marketplace_stock': float(sku.get('quantity', 0)),
                'last_sync_date': fields.Datetime.now(),
            }
            
            if existing:
                existing.write(values)
                return 'updated'
            else:
                MarketplaceProduct.create(values)
                return 'created'

    def action_fetch_orders(self):
        """Fetch orders from marketplace and create marketplace.order records"""
        self.ensure_one()

        created = 0
        updated = 0
        try:
            from datetime import datetime, timedelta
            
            time_to = datetime.now()
            time_from = time_to - timedelta(minutes=self.order_lookback_minutes)
            
            created = 0
            updated = 0
            
            if self.platform == 'shopee':
                from ..services.shopee_api import ShopeeAPI
                api = ShopeeAPI(self)
                
                orders = api.get_orders(
                    order_status_list=['READY_TO_SHIP', 'PROCESSED'],
                    create_time_from=int(time_from.timestamp()),
                    create_time_to=int(time_to.timestamp())
                )
                
                if orders and 'order_list' in orders:
                    for order in orders['order_list']:
                        result = self._process_shopee_order(order)
                        if result == 'created':
                            created += 1
                        elif result == 'updated':
                            updated += 1
            
            elif self.platform == 'lazada':
                from ..services.lazada_api import LazadaAPI
                api = LazadaAPI(self)
                
                orders = api.get_orders(
                    created_after=time_from.isoformat(),
                    status='pending'
                )
                
                if orders:
                    for order in orders:
                        result = self._process_lazada_order(order)
                        if result == 'created':
                            created += 1
                        elif result == 'updated':
                            updated += 1
            
            self.message_post(
                body=_('Fetched orders: %s created, %s updated') % (created, updated)
            )
            
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Orders Fetched'),
                    'message': _('Created: %s, Updated: %s') % (created, updated),
                    'type': 'success',
                    'sticky': False,
                }
            }
            
        except Exception as e:
            _logger.error(f'Fetch orders failed: {str(e)}')
            raise UserError(_('Failed to fetch orders: %s') % str(e))

    def _process_shopee_order(self, order_data):
        """Process a single Shopee order"""
        MarketplaceOrder = self.env['buz.marketplace.order']
        
        order_sn = order_data.get('order_sn')
        existing = MarketplaceOrder.search([
            ('account_id', '=', self.id),
            ('marketplace_order_id', '=', order_sn),
        ], limit=1)
        
        # Get order details
        from ..services.shopee_api import ShopeeAPI
        api = ShopeeAPI(self)
        order_detail = api.get_order_detail(order_sn)
        
        if not order_detail:
            return None
        
        values = {
            'account_id': self.id,
            'marketplace_order_id': order_sn,
            'name': order_sn,
            'order_status': order_data.get('order_status', '').lower(),
            'order_date': fields.Datetime.from_timestamp(order_data.get('create_time', 0)),
            'total_amount': order_detail.get('total_amount', 0.0),
            'state': 'imported',
        }
        
        if existing:
            existing.write(values)
            return 'updated'
        else:
            order = MarketplaceOrder.create(values)
            # Auto-create SO for paid orders
            if order.order_status in ['ready_to_ship', 'processed']:
                order.action_create_sale_order()
            return 'created'

    def _process_lazada_order(self, order_data):
        """Process a single Lazada order"""
        MarketplaceOrder = self.env['buz.marketplace.order']
        
        order_id = str(order_data.get('order_id'))
        existing = MarketplaceOrder.search([
            ('account_id', '=', self.id),
            ('marketplace_order_id', '=', order_id),
        ], limit=1)
        
        values = {
            'account_id': self.id,
            'marketplace_order_id': order_id,
            'name': order_data.get('order_number', order_id),
            'order_status': order_data.get('status', '').lower(),
            'order_date': fields.Datetime.now(),
            'total_amount': float(order_data.get('price', 0.0)),
            'state': 'imported',
        }
        
        if existing:
            existing.write(values)
            return 'updated'
        else:
            order = MarketplaceOrder.create(values)
            # Auto-create SO for paid orders
            if order.order_status in ['pending', 'ready_to_ship']:
                order.action_create_sale_order()
            return 'created'

    def action_refresh_token(self):
        """Refresh Shopee OAuth token"""
        self.ensure_one()
        
        if self.platform != 'shopee':
            raise UserError(_('Token refresh is only available for Shopee'))
        
        try:
            from ..services.shopee_api import ShopeeAPI
            api = ShopeeAPI(self)
            result = api.refresh_token()
            
            if result:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Token Refreshed'),
                        'message': _('Shopee token refreshed successfully'),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_('Token refresh failed'))
                
        except Exception as e:
            _logger.error(f'Token refresh failed: {str(e)}')
            raise UserError(_('Failed to refresh token: %s') % str(e))

    def action_view_products(self):
        """View marketplace products for this account"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Marketplace Products'),
            'res_model': 'buz.marketplace.product',
            'view_mode': 'tree,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }

    def action_view_orders(self):
        """View marketplace orders for this account"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Marketplace Orders'),
            'res_model': 'buz.marketplace.order',
            'view_mode': 'tree,form',
            'domain': [('account_id', '=', self.id)],
            'context': {'default_account_id': self.id},
        }

    @api.model
    def _cron_fetch_orders(self):
        accounts = self.search([('active', '=', True)])
        for account in accounts:
            try:
                account.action_fetch_orders()
            except Exception as e:
                _logger.error('Cron fetch orders failed for %s: %s', account.name, str(e))

    @api.model
    def _cron_refresh_tokens(self):
        accounts = self.search([
            ('active', '=', True),
            ('platform', '=', 'shopee'),
        ])
        for account in accounts:
            try:
                if account.shopee_refresh_token:
                    account.action_refresh_token()
            except Exception as e:
                _logger.error('Cron refresh token failed for %s: %s', account.name, str(e))
