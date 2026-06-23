# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class MarketplaceOrder(models.Model):
    _name = 'buz.marketplace.order'
    _description = 'Marketplace Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'order_date desc'

    name = fields.Char(
        string='Order Reference',
        required=True,
        index=True,
        tracking=True
    )
    account_id = fields.Many2one(
        'buz.marketplace.account',
        string='Marketplace Account',
        required=True,
        ondelete='cascade',
        check_company=True,
        tracking=True
    )
    marketplace_order_id = fields.Char(
        string='Marketplace Order ID',
        required=True,
        index=True
    )
    order_status = fields.Selection([
        ('unpaid', 'Unpaid'),
        ('paid', 'Paid'),
        ('ready_to_ship', 'Ready to Ship'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
        ('pending', 'Pending'),
        ('processed', 'Processed'),
    ], string='Marketplace Status', tracking=True)
    order_date = fields.Datetime(
        string='Order Date',
        tracking=True
    )
    buyer_name = fields.Char(
        string='Buyer Name'
    )
    buyer_phone = fields.Char(
        string='Buyer Phone'
    )
    buyer_address = fields.Text(
        string='Shipping Address'
    )
    buyer_partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        check_company=True
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        check_company=True,
        tracking=True
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        check_company=True
    )
    total_amount = fields.Float(
        string='Total Amount',
        digits='Product Price'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )
    notes = fields.Text(
        string='Notes'
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('imported', 'Imported'),
        ('so_created', 'SO Created'),
        ('delivery_validated', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft', tracking=True)
    line_ids = fields.One2many(
        'buz.marketplace.order.line',
        'order_id',
        string='Order Lines'
    )
    company_id = fields.Many2one(
        'res.company',
        related='account_id.company_id',
        store=True,
        index=True
    )

    _sql_constraints = [
        ('unique_marketplace_order',
         'UNIQUE(account_id, marketplace_order_id)',
         'This marketplace order already exists!')
    ]

    def action_create_sale_order(self):
        """Create SO, confirm, create & validate delivery from buffer location"""
        for order in self:
            if order.sale_order_id:
                raise UserError(_('Sale order already created for this marketplace order'))
            
            if not order.line_ids:
                raise UserError(_('No order lines found'))
            
            # Auto-create partner if needed
            partner = order._auto_create_partner()
            order.buyer_partner_id = partner
            
            # Prepare SO values
            so_vals = order._prepare_sale_order()
            sale_order = self.env['sale.order'].create(so_vals)
            
            # Create SO lines
            line_vals_list = order._prepare_sale_order_lines()
            for line_vals in line_vals_list:
                line_vals['order_id'] = sale_order.id
                self.env['sale.order.line'].create(line_vals)
            
            order.sale_order_id = sale_order
            order.state = 'so_created'
            
            # Confirm SO
            sale_order.action_confirm()
            
            # Get delivery order
            picking = sale_order.picking_ids.filtered(lambda p: p.state not in ['done', 'cancel'])
            if picking:
                order.picking_id = picking[0]
                
                # Override source location to buffer location
                if order.account_id.buffer_location_id:
                    for move in picking.move_ids:
                        move.location_id = order.account_id.buffer_location_id
                    for move_line in picking.move_line_ids:
                        move_line.location_id = order.account_id.buffer_location_id
                
                # Validate delivery
                picking[0].action_assign()
                
                # Set quantities
                for move_line in picking[0].move_line_ids:
                    move_line.quantity = move_line.reserved_quantity
                
                picking[0].button_validate()
                order.state = 'delivery_validated'
                
                # Log stock history for each line
                for line in order.line_ids:
                    if line.marketplace_product_id:
                        self.env['buz.marketplace.stock.history'].create({
                            'product_id': line.product_id.id,
                            'account_id': order.account_id.id,
                            'change_type': 'order_fulfillment',
                            'old_qty': line.marketplace_product_id.odoo_buffer_stock + line.quantity,
                            'new_qty': line.marketplace_product_id.odoo_buffer_stock,
                            'marketplace_qty': line.marketplace_product_id.marketplace_stock,
                            'notes': _('Fulfilled marketplace order %s') % order.name,
                        })
            
            order.message_post(
                body=_('Sale order %s created and validated') % sale_order.name
            )

    def _auto_create_partner(self):
        """Find or create res.partner by buyer details"""
        Partner = self.env['res.partner']
        
        if self.buyer_partner_id:
            return self.buyer_partner_id
        
        # Try to find existing partner by phone or name
        partner = False
        if self.buyer_phone:
            partner = Partner.search([('phone', '=', self.buyer_phone)], limit=1)
        
        if not partner and self.buyer_name:
            partner = Partner.search([('name', '=', self.buyer_name)], limit=1)
        
        if not partner:
            # Create new partner
            partner = Partner.create({
                'name': self.buyer_name or _('Marketplace Customer'),
                'phone': self.buyer_phone,
                'street': self.buyer_address,
                'customer_rank': 1,
                'company_id': self.company_id.id,
            })
        
        return partner

    def _prepare_sale_order(self):
        """Prepare SO values"""
        self.ensure_one()
        
        return {
            'partner_id': self.buyer_partner_id.id,
            'company_id': self.company_id.id,
            'warehouse_id': self.account_id.warehouse_id.id if self.account_id.warehouse_id else False,
            'origin': _('Marketplace: %s') % self.name,
            'note': self.notes,
        }

    def _prepare_sale_order_lines(self):
        """Prepare SO line values"""
        self.ensure_one()
        
        line_vals_list = []
        for line in self.line_ids:
            if not line.product_id:
                continue
            
            line_vals_list.append({
                'product_id': line.product_id.id,
                'name': line.product_name or line.product_id.display_name,
                'product_uom_qty': line.quantity,
                'product_uom': line.product_id.uom_id.id,
                'price_unit': line.price_unit,
            })
        
        return line_vals_list

    def action_view_sale_order(self):
        """View related sale order"""
        self.ensure_one()
        if not self.sale_order_id:
            raise UserError(_('No sale order created yet'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Sale Order'),
            'res_model': 'sale.order',
            'res_id': self.sale_order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_delivery(self):
        """View related delivery order"""
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No delivery order found'))
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Order'),
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
