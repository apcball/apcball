# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PosLiteReturnWizard(models.TransientModel):
    _name = 'pos.lite.return.wizard'
    _description = 'POS Lite Return Wizard'

    order_id = fields.Many2one('pos.lite.order', required=True, check_company=True)
    company_id = fields.Many2one(related='order_id.company_id', readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id', readonly=True)
    return_reason = fields.Text(string='Return Reason')
    line_ids = fields.One2many('pos.lite.return.wizard.line', 'wizard_id', string='Return Lines')

    @api.onchange('order_id')
    def _onchange_order_id(self):
        if not self.order_id:
            self.line_ids = [(5, 0, 0)]
            return

        lines = []
        for line in self.order_id.line_ids.filtered(lambda l: l.product_id):
            available_qty = line.available_return_qty if hasattr(line, 'available_return_qty') else line.qty
            if available_qty <= 0:
                continue
            lines.append((0, 0, {
                'order_line_id': line.id,
                'product_id': line.product_id.id,
                'description': line.description or line.product_id.display_name,
                'qty_available': available_qty,
                'qty': available_qty,
                'price_unit': line.price_unit,
                'discount': line.discount,
            }))
        self.line_ids = lines

    @api.constrains('line_ids')
    def _check_lines(self):
        for wizard in self:
            if not wizard.line_ids:
                raise ValidationError(_('Please select at least one product to return.'))
            for line in wizard.line_ids:
                if line.qty <= 0:
                    raise ValidationError(_('Return quantity must be greater than zero.'))
                if line.qty > line.qty_available:
                    raise ValidationError(_('Return quantity cannot exceed the available quantity.'))

    def action_confirm(self):
        self.ensure_one()
        if self.order_id.state != 'done':
            raise UserError(_('Only completed orders can be returned.'))
        if not self.line_ids:
            raise UserError(_('Please select at least one product to return.'))

        order = self.order_id
        line_commands = []
        for line in self.line_ids.filtered(lambda l: l.qty > 0):
            line_commands.append((0, 0, {
                'returned_from_line_id': line.order_line_id.id,
                'product_id': line.product_id.id,
                'description': line.description or line.product_id.display_name,
                'qty': line.qty,
                'price_unit': line.price_unit,
                'discount': line.discount,
            }))

        return_order_vals = {
            'company_id': order.company_id.id,
            'channel': order.channel,
            'customer_name': order.customer_name,
            'partner_id': order.partner_id.id if order.partner_id else False,
            'partner_phone': order.partner_phone,
            'partner_address': order.partner_address,
            'partner_tax_id': order.partner_tax_id,
            'warehouse_id': order.warehouse_id.id,
            'pricelist_id': order.pricelist_id.id,
            'note': '\n'.join([text for text in [order.note, self.return_reason and _('Return reason: %s') % self.return_reason] if text]),
            'is_return': True,
            'return_of_order_id': order.id,
            'line_ids': line_commands,
        }
        return_order = self.env['pos.lite.order'].create(return_order_vals)

        default_journal = return_order._get_default_payment_journal()
        refund_amount = return_order.amount_total
        payment_vals = {
            'order_id': return_order.id,
            'payment_method': 'cash',
            'amount': -refund_amount,
            'journal_id': default_journal.id if default_journal else False,
            'note': self.return_reason or _('Customer return refund'),
        }
        self.env['pos.lite.payment'].create(payment_vals)

        return_order.action_process_order()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Return Order'),
            'res_model': 'pos.lite.order',
            'view_mode': 'form',
            'res_id': return_order.id,
            'target': 'current',
        }


class PosLiteReturnWizardLine(models.TransientModel):
    _name = 'pos.lite.return.wizard.line'
    _description = 'POS Lite Return Wizard Line'

    wizard_id = fields.Many2one('pos.lite.return.wizard', required=True, ondelete='cascade')
    order_line_id = fields.Many2one('pos.lite.order.line', required=True, readonly=True)
    product_id = fields.Many2one('product.product', required=True, readonly=True)
    description = fields.Char(readonly=True)
    qty_available = fields.Float(readonly=True)
    qty = fields.Float(default=1.0)
    price_unit = fields.Monetary(required=True)
    currency_id = fields.Many2one(related='wizard_id.currency_id', readonly=True)
    discount = fields.Float(default=0.0)

    @api.constrains('qty')
    def _check_qty(self):
        for line in self:
            if line.qty <= 0:
                raise ValidationError(_('Return quantity must be greater than zero.'))
            if line.qty > line.qty_available:
                raise ValidationError(_('Return quantity cannot exceed the available quantity.'))
