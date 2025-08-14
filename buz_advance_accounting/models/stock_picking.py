# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    advance_accrual_ids = fields.One2many(
        'purchase.advance.accrual', 
        compute='_compute_advance_accrual_ids',
        string='Related Advance Accruals'
    )
    advance_accrual_count = fields.Integer(
        compute='_compute_advance_accrual_count',
        string='Advance Accrual Count'
    )
    purchase_order_id = fields.Many2one(
        'purchase.order',
        compute='_compute_purchase_order_id',
        string='Purchase Order',
        store=False
    )

    def _compute_purchase_order_id(self):
        for picking in self:
            purchase_order = False
            # Method 1: Try to find PO from origin
            if picking.origin:
                purchase_order = self.env['purchase.order'].search([('name', '=', picking.origin)], limit=1)
            
            # Method 2: Try to find PO from group_id
            if not purchase_order and picking.group_id:
                purchase_order = self.env['purchase.order'].search([('group_id', '=', picking.group_id.id)], limit=1)
            
            # Method 3: Try to find PO from move lines (using purchase module fields)
            if not purchase_order:
                for move in picking.move_ids:
                    # Check if purchase module is installed and has purchase_line_id
                    if hasattr(move, 'purchase_line_id') and move.purchase_line_id:
                        purchase_order = move.purchase_line_id.order_id
                        break
            
            picking.purchase_order_id = purchase_order

    def _compute_advance_accrual_ids(self):
        for picking in self:
            if picking.purchase_order_id:
                picking.advance_accrual_ids = picking.purchase_order_id.advance_accrual_ids
            else:
                picking.advance_accrual_ids = False

    @api.depends('advance_accrual_ids')
    def _compute_advance_accrual_count(self):
        for picking in self:
            picking.advance_accrual_count = len(picking.advance_accrual_ids)

    def action_view_advance_accruals(self):
        """View advance accrual entries related to this picking's PO"""
        self.ensure_one()
        if not self.purchase_order_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Purchase Order'),
                    'message': _('This picking is not linked to any Purchase Order.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        action = self.env.ref('buz_advance_accounting.action_purchase_advance_accrual').read()[0]
        action['domain'] = [('purchase_id', '=', self.purchase_order_id.id)]
        action['context'] = {
            'default_purchase_id': self.purchase_order_id.id,
        }
        return action

    def action_create_advance_accrual(self):
        """Create advance accrual from picking"""
        self.ensure_one()
        if not self.purchase_order_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Purchase Order'),
                    'message': _('This picking is not linked to any Purchase Order.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Advance Accrual'),
            'res_model': 'purchase.advance.bill.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('buz_advance_accounting.view_advance_bill_wizard_form').id,
            'target': 'new',
            'context': {
                'default_purchase_id': self.purchase_order_id.id,
                'default_amount': self.purchase_order_id.amount_total,
                'default_currency_id': self.purchase_order_id.currency_id.id,
            }
        }

    def action_reverse_all_advance_accruals(self):
        """Reverse all advance accrual entries from picking"""
        self.ensure_one()
        if not self.purchase_order_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('No Purchase Order'),
                    'message': _('This picking is not linked to any Purchase Order.'),
                    'type': 'warning',
                    'sticky': False,
                }
            }
        
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reverse All Accrual Entries'),
            'res_model': 'reverse.accrual.wizard',
            'view_mode': 'form',
            'view_id': self.env.ref('buz_advance_accounting.view_reverse_accrual_wizard_form').id,
            'target': 'new',
            'context': {
                'default_purchase_id': self.purchase_order_id.id,
            }
        }
