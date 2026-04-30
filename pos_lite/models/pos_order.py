# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare


WALK_IN_CUSTOMER_NAME = 'Walk-in Customer'


class PosLiteOrder(models.Model):
    _name = 'pos.lite.order'
    _description = 'POS Lite Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    _rec_name = 'name'

    name = fields.Char(default='/', copy=False, readonly=True, tracking=True)
    company_id = fields.Many2one('res.company', required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('paid', 'Paid'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled'),
    ], default='draft', required=True, tracking=True)
    channel = fields.Selection([
        ('phone', 'Phone'),
        ('line', 'LINE'),
        ('walkin', 'Walk-in'),
        ('other', 'Other'),
    ], default='phone', required=True, tracking=True)
    customer_name = fields.Char(tracking=True)
    partner_id = fields.Many2one('res.partner', tracking=True, check_company=True)
    partner_phone = fields.Char(tracking=True)
    partner_address = fields.Char(tracking=True)
    partner_tax_id = fields.Char(tracking=True)
    warehouse_id = fields.Many2one(
        'stock.warehouse',
        required=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
        check_company=True,
    )
    pricelist_id = fields.Many2one(
        'product.pricelist',
        required=True,
        domain="['|', ('company_id', '=', False), ('company_id', '=', company_id)]",
        tracking=True,
        check_company=True,
    )
    line_ids = fields.One2many('pos.lite.order.line', 'order_id', string='Order Lines')
    payment_ids = fields.One2many('pos.lite.payment', 'order_id', string='Payments')
    amount_untaxed = fields.Monetary(compute='_compute_amounts', store=True)
    amount_tax = fields.Monetary(compute='_compute_amounts', store=True)
    amount_total = fields.Monetary(compute='_compute_amounts', store=True)
    amount_paid = fields.Monetary(compute='_compute_amounts', store=True)
    amount_residual = fields.Monetary(compute='_compute_amounts', store=True)
    amount_change = fields.Monetary(compute='_compute_amounts', store=True)
    invoice_id = fields.Many2one('account.move', readonly=True, copy=False)
    picking_id = fields.Many2one('stock.picking', readonly=True, copy=False)
    is_return = fields.Boolean(default=False, copy=False, tracking=True)
    return_of_order_id = fields.Many2one('pos.lite.order', readonly=True, copy=False, tracking=True, index=True)
    return_order_ids = fields.One2many('pos.lite.order', 'return_of_order_id', string='Return Orders')
    return_reason = fields.Text(copy=False)
    note = fields.Text()

    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Order number must be unique.'),
    ]

    @api.depends('line_ids.price_subtotal', 'line_ids.price_tax', 'payment_ids.amount', 'is_return')
    def _compute_amounts(self):
        for order in self:
            untaxed = sum(order.line_ids.mapped('price_subtotal'))
            tax = sum(order.line_ids.mapped('price_tax'))
            paid = sum(order.payment_ids.mapped('amount'))
            total = untaxed + tax
            paid_display = abs(paid) if order.is_return else paid
            order.amount_untaxed = untaxed
            order.amount_tax = tax
            order.amount_total = total
            order.amount_paid = paid_display
            order.amount_residual = max(total - paid_display, 0.0)
            order.amount_change = max(paid_display - total, 0.0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/' or not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('pos.lite.order') or '/'
        return super().create(vals_list)

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        if self.partner_id:
            self.customer_name = self.partner_id.name
            self.partner_phone = self.partner_id.phone or self.partner_id.mobile
            self.partner_address = self.partner_id.street
            self.partner_tax_id = self.partner_id.vat
            if getattr(self.partner_id, 'property_product_pricelist', False):
                self.pricelist_id = self.partner_id.property_product_pricelist
        else:
            self.customer_name = False
            self.partner_phone = False
            self.partner_address = False
            self.partner_tax_id = False

    @api.onchange('company_id')
    def _onchange_company_id(self):
        config = self.env['pos.lite.config'].get_default_config(self.company_id)
        if config:
            self.warehouse_id = config.warehouse_id
            self.pricelist_id = config.pricelist_id

    def _get_walk_in_partner(self):
        self.ensure_one()
        partner = self.env['res.partner'].search([
            ('name', '=', WALK_IN_CUSTOMER_NAME),
            ('company_id', 'in', [False, self.company_id.id]),
        ], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': WALK_IN_CUSTOMER_NAME,
                'company_id': False,
                'customer_rank': 1,
            })
        return partner

    def _get_or_create_customer_partner(self):
        self.ensure_one()
        if self.partner_id:
            return self.partner_id
        name = self.customer_name or WALK_IN_CUSTOMER_NAME
        partner = self.env['res.partner'].search([
            ('name', '=', name),
            ('company_id', 'in', [False, self.company_id.id]),
        ], limit=1)
        if not partner and self.partner_phone:
            partner = self.env['res.partner'].search([
                ('phone', '=', self.partner_phone),
                ('company_id', 'in', [False, self.company_id.id]),
            ], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': name,
                'company_id': False,
                'customer_rank': 1,
                'phone': self.partner_phone,
                'street': self.partner_address,
                'vat': self.partner_tax_id,
            })
        return partner

    def _get_default_payment_journal(self):
        self.ensure_one()
        config = self.env['pos.lite.config'].get_default_config(self.company_id)
        if config and config.journal_id:
            return config.journal_id
        return self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', 'in', ('cash', 'bank')),
        ], limit=1)

    def _prepare_invoice_vals(self):
        self.ensure_one()
        partner = self._get_or_create_customer_partner()
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'sale'),
        ], limit=1)
        if not journal:
            raise UserError(_('No sales journal found for company %s.') % self.company_id.display_name)
        line_vals = []
        for line in self.line_ids:
            taxes = line.product_id.taxes_id.filtered(lambda t: t.company_id in (False, self.company_id))
            line_vals.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.description or line.product_id.display_name,
                'quantity': line.qty,
                'price_unit': line.price_unit,
                'discount': line.discount,
                'tax_ids': [(6, 0, taxes.ids)],
                'product_uom_id': line.product_id.uom_id.id,
            }))
        return {
            'move_type': 'out_refund' if self.is_return else 'out_invoice',
            'company_id': self.company_id.id,
            'partner_id': partner.id,
            'invoice_origin': self.name,
            'invoice_payment_term_id': False,
            'journal_id': journal.id,
            'invoice_line_ids': line_vals,
        }

    def _prepare_picking_vals(self):
        self.ensure_one()
        partner = self._get_or_create_customer_partner()
        if self.is_return:
            picking_type = self.warehouse_id.in_type_id
            if not picking_type:
                raise UserError(_('No incoming picking type found for warehouse %s.') % self.warehouse_id.display_name)
        else:
            picking_type = self.warehouse_id.out_type_id
            if not picking_type:
                raise UserError(_('No outgoing picking type found for warehouse %s.') % self.warehouse_id.display_name)
        customer_location = self.env.ref('stock.stock_location_customers', raise_if_not_found=False)
        if not customer_location:
            customer_location = self.env['stock.location'].search([('usage', '=', 'customer')], limit=1)
        if not customer_location:
            raise UserError(_('No customer location could be found for stock delivery.'))
        moves = []
        for line in self.line_ids.filtered(lambda l: l.product_id.type != 'service' and l.qty > 0):
            location_id = customer_location.id if self.is_return else self.warehouse_id.lot_stock_id.id
            location_dest_id = self.warehouse_id.lot_stock_id.id if self.is_return else customer_location.id
            moves.append((0, 0, {
                'name': line.description or line.product_id.display_name,
                'product_id': line.product_id.id,
                'product_uom_qty': line.qty,
                'product_uom': line.product_id.uom_id.id,
                'location_id': location_id,
                'location_dest_id': location_dest_id,
            }))
        return {
            'picking_type_id': picking_type.id,
            'partner_id': partner.id,
            'origin': self.name,
            'company_id': self.company_id.id,
            'location_id': self.warehouse_id.lot_stock_id.id if not self.is_return else customer_location.id,
            'location_dest_id': customer_location.id if not self.is_return else self.warehouse_id.lot_stock_id.id,
            'move_ids_without_package': moves,
        }

    def _process_stock_picking(self, picking):
        picking.action_confirm()
        picking.action_assign()
        for move in picking.move_ids_without_package:
            for move_line in move.move_line_ids:
                reserved_qty = move_line.reserved_uom_qty if 'reserved_uom_qty' in move_line._fields else 0.0
                done_qty = reserved_qty or move.product_uom_qty
                if 'quantity' in move_line._fields:
                    move_line.quantity = done_qty
                elif 'qty_done' in move_line._fields:
                    move_line.qty_done = done_qty
            if not move.move_line_ids:
                move._action_assign()
        result = picking.button_validate()
        if isinstance(result, dict) and result.get('res_model') == 'stock.immediate.transfer':
            wizard = self.env['stock.immediate.transfer'].with_context(result.get('context', {})).create({
                'pick_ids': [(6, 0, picking.ids)],
            })
            wizard.process()
        elif isinstance(result, dict) and result.get('res_model') == 'stock.backorder.confirmation':
            wizard = self.env['stock.backorder.confirmation'].with_context(result.get('context', {})).create({})
            wizard.process_cancel_backorder()

    def action_register_payment(self):
        self.ensure_one()
        if self.state != 'draft':
            raise UserError(_('Only draft orders can receive a payment.'))
        payment = self.payment_ids[:1]
        default_journal = self._get_default_payment_journal()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Register Payment'),
            'res_model': 'pos.lite.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_payment_method': payment.payment_method if payment else 'cash',
                'default_amount': self.amount_residual or self.amount_total,
                'default_journal_id': payment.journal_id.id if payment and payment.journal_id else (default_journal.id if default_journal else False),
            },
        }

    def action_process_order(self):
        for order in self:
            if order.state != 'draft':
                continue
            if not order.line_ids:
                raise UserError(_('Please add at least one order line.'))
            if len(order.payment_ids) != 1:
                raise UserError(_('Exactly one payment is required before processing the order.'))
            paid_amount = abs(sum(order.payment_ids.mapped('amount')))
            if float_compare(paid_amount, order.amount_total, precision_rounding=order.currency_id.rounding) < 0:
                if order.is_return:
                    raise UserError(_('Refund payment must cover the full return total before the documents can be created.'))
                raise UserError(_('Payment must cover the full total before stock and invoice can be created.'))
            if not order.partner_id:
                order.partner_id = order._get_or_create_customer_partner().id
            if not order.invoice_id:
                invoice = self.env['account.move'].create(order._prepare_invoice_vals())
                invoice.action_post()
                order.invoice_id = invoice.id
            if not order.picking_id:
                picking = self.env['stock.picking'].create(order._prepare_picking_vals())
                order.picking_id = picking.id
                order._process_stock_picking(picking)
            order.state = 'paid'
            if order.is_return:
                order.action_done()
        return True

    def action_create_return(self):
        self.ensure_one()
        if self.state != 'done':
            raise UserError(_('Only completed orders can be returned.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Create Return'),
            'res_model': 'pos.lite.return.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
            },
        }

    def action_done(self):
        for order in self:
            if order.state != 'paid':
                raise UserError(_('Only paid orders can be marked as done.'))
            if not order.invoice_id or order.invoice_id.state != 'posted':
                raise UserError(_('The order invoice must be posted before marking the order as done.'))
            if not order.picking_id or order.picking_id.state != 'done':
                raise UserError(_('The stock picking must be completed before marking the order as done.'))
        self.write({'state': 'done'})

    def action_cancel(self):
        for order in self:
            if order.state == 'done':
                raise UserError(_('Cannot cancel a completed order.'))
            if order.invoice_id and order.invoice_id.state == 'posted':
                raise UserError(_('Cannot cancel an order with a posted invoice.'))
            if order.picking_id and order.picking_id.state == 'done':
                raise UserError(_('Cannot cancel an order with a completed stock transfer.'))
            if order.invoice_id:
                order.invoice_id.unlink()
                order.invoice_id = False
            if order.picking_id:
                if order.picking_id.state != 'cancel':
                    order.picking_id.action_cancel()
                order.picking_id.unlink()
                order.picking_id = False
            if order.payment_ids:
                order.payment_ids.unlink()
        self.write({'state': 'cancelled'})

    def action_view_invoice(self):
        self.ensure_one()
        if not self.invoice_id:
            raise UserError(_('No invoice has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Credit Note') if self.is_return else _('Invoice'),
            'res_model': 'account.move',
            'view_mode': 'form',
            'res_id': self.invoice_id.id,
            'target': 'current',
        }

    def action_view_picking(self):
        self.ensure_one()
        if not self.picking_id:
            raise UserError(_('No stock picking has been created yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Delivery Order'),
            'res_model': 'stock.picking',
            'view_mode': 'form',
            'res_id': self.picking_id.id,
            'target': 'current',
        }

    def action_print_receipt_58mm(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_receipt_58mm').report_action(self)

    def action_print_receipt_80mm(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_receipt_80mm').report_action(self)

    def action_print_receipt_a4(self):
        self.ensure_one()
        return self.env.ref('pos_lite.action_report_pos_lite_receipt_a4').report_action(self)


class PosLiteOrderLine(models.Model):
    _name = 'pos.lite.order.line'
    _description = 'POS Lite Order Line'
    _order = 'id asc'

    order_id = fields.Many2one('pos.lite.order', required=True, ondelete='cascade', check_company=True)
    company_id = fields.Many2one(related='order_id.company_id', store=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id', store=True, readonly=True)
    product_id = fields.Many2one('product.product', required=True, domain="[('sale_ok', '=', True)]", check_company=True)
    description = fields.Char()
    qty = fields.Float(default=1.0)
    price_unit = fields.Monetary(required=True)
    discount = fields.Float(default=0.0)
    returned_from_line_id = fields.Many2one('pos.lite.order.line', copy=False, index=True)
    return_line_ids = fields.One2many('pos.lite.order.line', 'returned_from_line_id', string='Return Lines')
    returned_qty = fields.Float(compute='_compute_returned_qty', store=False)
    available_return_qty = fields.Float(compute='_compute_returned_qty', store=False)
    price_subtotal = fields.Monetary(compute='_compute_amounts', store=True)
    price_tax = fields.Monetary(compute='_compute_amounts', store=True)
    price_total = fields.Monetary(compute='_compute_amounts', store=True)

    @api.depends('return_line_ids.qty')
    def _compute_returned_qty(self):
        for line in self:
            returned_qty = sum(line.return_line_ids.mapped('qty'))
            line.returned_qty = returned_qty
            line.available_return_qty = max(line.qty - returned_qty, 0.0)

    @api.depends('qty', 'price_unit', 'discount', 'product_id', 'order_id.partner_id', 'order_id.pricelist_id')
    def _compute_amounts(self):
        for line in self:
            price = line.price_unit or 0.0
            discounted = price * (1.0 - (line.discount or 0.0) / 100.0)
            taxes = line.product_id.taxes_id.filtered(lambda t: t.company_id in (False, line.company_id))
            if taxes:
                tax_res = taxes.compute_all(
                    discounted,
                    currency=line.currency_id,
                    quantity=line.qty or 1.0,
                    product=line.product_id,
                    partner=line.order_id.partner_id,
                )
                line.price_subtotal = tax_res['total_excluded']
                line.price_tax = tax_res['total_included'] - tax_res['total_excluded']
                line.price_total = tax_res['total_included']
            else:
                subtotal = discounted * (line.qty or 1.0)
                line.price_subtotal = subtotal
                line.price_tax = 0.0
                line.price_total = subtotal

    @api.onchange('product_id', 'qty', 'order_id.pricelist_id', 'order_id.partner_id')
    def _onchange_product_id(self):
        for line in self:
            if not line.product_id:
                line.description = False
                continue
            line.description = line.product_id.display_name
            line.qty = line.qty or 1.0
            pricelist = line.order_id.pricelist_id
            partner = line.order_id.partner_id
            price = line.product_id.lst_price
            if pricelist:
                try:
                    if hasattr(pricelist, '_get_product_price'):
                        price = pricelist._get_product_price(line.product_id, line.qty or 1.0, partner)
                    else:
                        price = pricelist._get_product_price_rule(line.product_id, line.qty or 1.0, partner)[0]
                except (AttributeError, IndexError, TypeError, ValueError):
                    price = line.product_id.lst_price
            line.price_unit = price
            if line.discount is None:
                line.discount = 0.0

    @api.constrains('qty', 'price_unit', 'discount')
    def _check_values(self):
        for line in self:
            if line.qty <= 0:
                raise ValidationError(_('Quantity must be greater than zero.'))
            if line.discount < 0 or line.discount > 100:
                raise ValidationError(_('Discount must be between 0 and 100 percent.'))
