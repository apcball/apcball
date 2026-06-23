# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class MarketplaceProduct(models.Model):
    _name = 'buz.marketplace.product'
    _description = 'Marketplace Product'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    account_id = fields.Many2one(
        'buz.marketplace.account',
        string='Marketplace Account',
        required=True,
        ondelete='cascade',
        check_company=True,
        tracking=True
    )
    product_tmpl_id = fields.Many2one(
        'product.template',
        string='Product Template',
        check_company=True,
        tracking=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product Variant',
        check_company=True,
        tracking=True
    )
    marketplace_sku = fields.Char(
        string='Marketplace SKU',
        index=True
    )
    marketplace_item_id = fields.Char(
        string='Marketplace Item ID',
        required=True,
        index=True
    )
    marketplace_variation_id = fields.Char(
        string='Marketplace Variation ID',
        index=True
    )
    marketplace_name = fields.Char(
        string='Marketplace Name',
        tracking=True
    )
    marketplace_price = fields.Float(
        string='Marketplace Price',
        digits='Product Price',
        tracking=True
    )
    marketplace_stock = fields.Float(
        string='Marketplace Stock',
        digits='Product Unit of Measure',
        tracking=True
    )
    odoo_buffer_stock = fields.Float(
        string='Odoo Buffer Stock',
        compute='_compute_odoo_buffer_stock',
        store=True,
        digits='Product Unit of Measure'
    )
    initial_stock_qty = fields.Float(
        string='Initial Buffer Stock',
        digits='Product Unit of Measure',
        help='Target stock quantity in buffer location'
    )
    last_sync_date = fields.Datetime(
        string='Last Sync Date'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True
    )
    company_id = fields.Many2one(
        'res.company',
        related='account_id.company_id',
        store=True,
        index=True
    )

    _sql_constraints = [
        ('unique_marketplace_product',
         'UNIQUE(account_id, marketplace_item_id, marketplace_variation_id)',
         'This marketplace product already exists for this account!')
    ]

    @api.depends('product_id', 'account_id.buffer_location_id')
    def _compute_odoo_buffer_stock(self):
        """Compute available stock in buffer location"""
        for record in self:
            if record.product_id and record.account_id.buffer_location_id:
                quants = self.env['stock.quant'].search([
                    ('product_id', '=', record.product_id.id),
                    ('location_id', '=', record.account_id.buffer_location_id.id),
                ])
                record.odoo_buffer_stock = sum(quants.mapped('quantity')) - sum(quants.mapped('reserved_quantity'))
            else:
                record.odoo_buffer_stock = 0.0

    def action_fetch_stock(self):
        """Fetch current stock from marketplace"""
        for record in self:
            try:
                old_qty = record.marketplace_stock
                
                if record.account_id.platform == 'shopee':
                    from ..services.shopee_api import ShopeeAPI
                    api = ShopeeAPI(record.account_id)
                    
                    item_detail = api.get_item_detail([int(record.marketplace_item_id)])
                    if item_detail and 'item_list' in item_detail:
                        item = item_detail['item_list'][0]
                        
                        if record.marketplace_variation_id:
                            # Find variation
                            for model in item.get('model', []):
                                if str(model.get('model_id')) == record.marketplace_variation_id:
                                    new_qty = float(model.get('stock_info', [{}])[0].get('stock', 0))
                                    record.marketplace_stock = new_qty
                                    break
                        else:
                            new_qty = float(item.get('stock_info', [{}])[0].get('stock', 0))
                            record.marketplace_stock = new_qty
                
                elif record.account_id.platform == 'lazada':
                    from ..services.lazada_api import LazadaAPI
                    api = LazadaAPI(record.account_id)
                    
                    products = api.get_products(filter='all', limit=1)
                    if products:
                        # Find matching product
                        for product in products:
                            if str(product.get('item_id')) == record.marketplace_item_id:
                                skus = product.get('skus', [])
                                if record.marketplace_variation_id:
                                    for sku in skus:
                                        if str(sku.get('sku_id')) == record.marketplace_variation_id:
                                            new_qty = float(sku.get('quantity', 0))
                                            record.marketplace_stock = new_qty
                                            break
                                else:
                                    if skus:
                                        new_qty = float(skus[0].get('quantity', 0))
                                        record.marketplace_stock = new_qty
                                break
                
                record.last_sync_date = fields.Datetime.now()
                
                # Log history
                self.env['buz.marketplace.stock.history'].create({
                    'product_id': record.product_id.id,
                    'account_id': record.account_id.id,
                    'change_type': 'fetch',
                    'old_qty': old_qty,
                    'new_qty': record.marketplace_stock,
                    'marketplace_qty': record.marketplace_stock,
                    'notes': _('Fetched stock from %s') % record.account_id.platform,
                })
                
            except Exception as e:
                _logger.error(f'Failed to fetch stock for {record.marketplace_name}: {str(e)}')
                raise UserError(_('Failed to fetch stock: %s') % str(e))

    def action_fetch_price(self):
        """Fetch current price from marketplace"""
        # Similar to action_fetch_stock but for price
        for record in self:
            try:
                if record.account_id.platform == 'shopee':
                    from ..services.shopee_api import ShopeeAPI
                    api = ShopeeAPI(record.account_id)
                    
                    item_detail = api.get_item_detail([int(record.marketplace_item_id)])
                    if item_detail and 'item_list' in item_detail:
                        item = item_detail['item_list'][0]
                        
                        if record.marketplace_variation_id:
                            for model in item.get('model', []):
                                if str(model.get('model_id')) == record.marketplace_variation_id:
                                    record.marketplace_price = model.get('price', 0.0)
                                    break
                        else:
                            record.marketplace_price = item.get('price', 0.0)
                
                elif record.account_id.platform == 'lazada':
                    from ..services.lazada_api import LazadaAPI
                    api = LazadaAPI(record.account_id)
                    
                    products = api.get_products(filter='all', limit=1)
                    if products:
                        for product in products:
                            if str(product.get('item_id')) == record.marketplace_item_id:
                                skus = product.get('skus', [])
                                if record.marketplace_variation_id:
                                    for sku in skus:
                                        if str(sku.get('sku_id')) == record.marketplace_variation_id:
                                            record.marketplace_price = float(sku.get('price', 0.0))
                                            break
                                else:
                                    if skus:
                                        record.marketplace_price = float(skus[0].get('price', 0.0))
                                break
                
                record.last_sync_date = fields.Datetime.now()
                
            except Exception as e:
                _logger.error(f'Failed to fetch price for {record.marketplace_name}: {str(e)}')
                raise UserError(_('Failed to fetch price: %s') % str(e))

    def action_push_stock(self, stock_qty=None):
        """Push stock to marketplace"""
        for record in self:
            try:
                if stock_qty is None:
                    stock_qty = record.odoo_buffer_stock
                
                old_qty = record.marketplace_stock
                
                if record.account_id.platform == 'shopee':
                    from ..services.shopee_api import ShopeeAPI
                    api = ShopeeAPI(record.account_id)
                    
                    variation_id = int(record.marketplace_variation_id) if record.marketplace_variation_id else 0
                    stock_list = [(variation_id, int(stock_qty))]
                    
                    result = api.update_stock(int(record.marketplace_item_id), stock_list)
                    if result:
                        record.marketplace_stock = stock_qty
                
                elif record.account_id.platform == 'lazada':
                    from ..services.lazada_api import LazadaAPI
                    api = LazadaAPI(record.account_id)
                    
                    result = api.update_stock(record.marketplace_sku, int(stock_qty))
                    if result:
                        record.marketplace_stock = stock_qty
                
                record.last_sync_date = fields.Datetime.now()
                
                # Log history
                self.env['buz.marketplace.stock.history'].create({
                    'product_id': record.product_id.id,
                    'account_id': record.account_id.id,
                    'change_type': 'push',
                    'old_qty': old_qty,
                    'new_qty': record.marketplace_stock,
                    'marketplace_qty': record.marketplace_stock,
                    'notes': _('Pushed stock to %s') % record.account_id.platform,
                })
                
            except Exception as e:
                _logger.error(f'Failed to push stock for {record.marketplace_name}: {str(e)}')
                raise UserError(_('Failed to push stock: %s') % str(e))

    def action_refill(self):
        """Refill buffer stock from main location to initial quantity"""
        for record in self:
            if not record.product_id:
                raise UserError(_('No Odoo product linked to %s') % record.marketplace_name)
            
            if not record.account_id.buffer_location_id:
                raise UserError(_('No buffer location configured for account %s') % record.account_id.name)
            
            if not record.account_id.warehouse_id:
                raise UserError(_('No warehouse configured for account %s') % record.account_id.name)
            
            needed_qty = record.initial_stock_qty - record.odoo_buffer_stock
            
            if needed_qty <= 0:
                raise UserError(_('Buffer stock is already at or above initial quantity'))
            
            # Get main stock location
            main_location = record.account_id.warehouse_id.lot_stock_id
            
            # Create internal transfer
            picking_type = self.env['stock.picking.type'].search([
                ('code', '=', 'internal'),
                ('warehouse_id', '=', record.account_id.warehouse_id.id),
            ], limit=1)
            
            if not picking_type:
                raise UserError(_('No internal transfer type found for warehouse'))
            
            picking = self.env['stock.picking'].create({
                'picking_type_id': picking_type.id,
                'location_id': main_location.id,
                'location_dest_id': record.account_id.buffer_location_id.id,
                'origin': _('Refill: %s') % record.marketplace_name,
            })
            
            move = self.env['stock.move'].create({
                'name': record.product_id.display_name,
                'product_id': record.product_id.id,
                'product_uom_qty': needed_qty,
                'product_uom': record.product_id.uom_id.id,
                'picking_id': picking.id,
                'location_id': main_location.id,
                'location_dest_id': record.account_id.buffer_location_id.id,
            })
            
            picking.action_confirm()
            picking.action_assign()
            
            # Set move quantities
            for move_line in picking.move_line_ids:
                move_line.quantity = move_line.reserved_quantity
            
            picking.button_validate()
            
            # Log history
            self.env['buz.marketplace.stock.history'].create({
                'product_id': record.product_id.id,
                'account_id': record.account_id.id,
                'change_type': 'refill',
                'old_qty': record.odoo_buffer_stock - needed_qty,
                'new_qty': record.odoo_buffer_stock,
                'marketplace_qty': record.marketplace_stock,
                'stock_move_id': move.id,
                'notes': _('Refilled %s units from main stock') % needed_qty,
            })
            
            record.message_post(
                body=_('Refilled %s units from main stock. Picking: %s') % (needed_qty, picking.name)
            )

    def action_link_product(self):
        """Open wizard to link to Odoo product"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Link Product'),
            'res_model': 'product.product',
            'view_mode': 'tree,form',
            'target': 'new',
            'domain': [('type', 'in', ['product', 'consu'])],
            'context': {
                'marketplace_product_id': self.id,
            },
        }
