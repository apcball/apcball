# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class SaleOrder(models.Model):
    """Extend Sale Order to add credit note creation"""

    _inherit = 'sale.order'

    has_refundable_lines = fields.Boolean(
        string='Has Refundable Lines',
        compute='_compute_has_refundable_lines',
        store=True,
        help='Whether the order has lines that can be refunded'
    )

    @api.depends('order_line.qty_delivered', 'order_line.qty_invoiced', 'order_line.product_uom_qty')
    def _compute_has_refundable_lines(self):
        """Compute if SO has refundable lines"""
        for order in self:
            # Refundable if delivered > invoiced or if there's refundable quantity
            order.has_refundable_lines = any(
                line.qty_delivered > line.qty_invoiced
                for line in order.order_line
                if line.product_id.type in ['consu', 'product']
            )

    def action_open_so_credit_note_wizard(self):
        """Open wizard to create credit note from SO"""
        self.ensure_one()

        # Check if SO is confirmed
        if self.state != 'sale':
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cannot Create Credit Note',
                    'message': 'Credit notes can only be created from confirmed sale orders.',
                    'type': 'warning',
                    'sticky': True,
                }
            }

        # Filter refundable lines (delivered > invoiced)
        refundable_lines = self.order_line.filtered(
            lambda l: l.product_id.type in ['consu', 'product']
            and l.qty_delivered > l.qty_invoiced
        )

        if not refundable_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Refundable Lines',
                    'message': 'This order has no refundable lines.',
                    'type': 'info',
                    'sticky': False,
                }
            }

        journal = self.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('No sales journal was found for company %s.') % self.company_id.display_name)

        # Create wizard with refundable lines
        wizard = self.env['so.credit.note.wizard'].create({
            'sale_order_id': self.id,
            'journal_id': journal.id,
        })

        # Create wizard lines
        for line in refundable_lines:
            qty_to_refund = line.qty_delivered - line.qty_invoiced
            self.env['so.credit.note.wizard.line'].create({
                'wizard_id': wizard.id,
                'so_line_id': line.id,
                'product_id': line.product_id.id,
                'ordered_qty': line.product_uom_qty,
                'delivered_qty': line.qty_delivered,
                'invoiced_qty': line.qty_invoiced,
                'qty_to_refund': qty_to_refund,
                'price_unit': line.price_unit,
                'selected': True,
            })

        # Open wizard form
        return {
            'name': 'Create SO Credit Note',
            'type': 'ir.actions.act_window',
            'res_model': 'so.credit.note.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
