# -*- coding: utf-8 -*-

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PurchaseOrder(models.Model):
    """Extend Purchase Order to add credit note creation"""

    _inherit = 'purchase.order'

    has_negative_lines = fields.Boolean(
        string='Has Negative Lines',
        compute='_compute_has_negative_lines',
        store=True,
        help='Whether the order has lines with negative quantity'
    )

    @api.depends('order_line.product_qty')
    def _compute_has_negative_lines(self):
        """Compute if PO has negative quantity lines"""
        for order in self:
            order.has_negative_lines = any(
                line.product_qty < 0 for line in order.order_line
            )

    def action_open_po_credit_note_wizard(self):
        """Open wizard to create credit note from PO"""
        self.ensure_one()

        # Check if PO is in appropriate state
        if self.state not in ['purchase', 'done']:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Cannot Create Credit Note',
                    'message': 'Credit notes can only be created from confirmed or done purchase orders.',
                    'type': 'warning',
                    'sticky': True,
                }
            }

        # Filter lines with negative quantity
        negative_lines = self.order_line.filtered(lambda l: l.product_qty < 0)

        if not negative_lines:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'No Negative Lines',
                    'message': 'This order has no lines with negative quantity.',
                    'type': 'info',
                    'sticky': False,
                }
            }

        journal = self.env['account.journal'].search([
            ('type', '=', 'purchase'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_('No purchase journal was found for company %s.') % self.company_id.display_name)

        # Create wizard with negative lines
        wizard = self.env['po.credit.note.wizard'].create({
            'purchase_order_id': self.id,
            'journal_id': journal.id,
        })

        # Create wizard lines
        for line in negative_lines:
            self.env['po.credit.note.wizard.line'].create({
                'wizard_id': wizard.id,
                'po_line_id': line.id,
                'product_id': line.product_id.id,
                'product_qty': abs(line.product_qty),
                'price_unit': line.price_unit,
                'selected': True,
            })

        # Open wizard form
        return {
            'name': 'Create PO Credit Note',
            'type': 'ir.actions.act_window',
            'res_model': 'po.credit.note.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
