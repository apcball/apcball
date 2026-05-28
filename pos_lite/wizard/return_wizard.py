from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class PosLiteReturnWizard(models.TransientModel):
    _name = 'pos.lite.return.wizard'
    _description = 'POS Lite Return Wizard'

    order_id = fields.Many2one('pos.lite.order', required=True, check_company=True)
    company_id = fields.Many2one(related='order_id.company_id', readonly=True)
    currency_id = fields.Many2one(related='order_id.currency_id', readonly=True)
    return_reason = fields.Text(string='Return Reason')
    is_exchange = fields.Boolean(default=False)

    # Refund payment method
    refund_payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('transfer', 'Transfer'),
        ('card', 'Card'),
        ('promptpay', 'PromptPay'),
        ('other', 'Other'),
    ], default='cash', string='Refund Method', required=True)
    refund_journal_id = fields.Many2one(
        'account.journal', string='Refund Journal',
        domain="[('type', 'in', ('cash', 'bank')), ('company_id', '=', company_id)]",
        check_company=True,
    )

    # Exchange fields
    exchange_partner_id = fields.Many2one(
        'res.partner', string='Exchange Customer',
        context="{'pos_lite_partner_search': 1}", check_company=True,
    )
    exchange_warehouse_id = fields.Many2one(
        'stock.warehouse', string='Exchange Warehouse',
        domain="[('company_id', '=', company_id)]", check_company=True,
    )
    exchange_channel = fields.Selection([
        ('phone', 'Phone'), ('line', 'LINE'), ('walkin', 'Walk-in'), ('other', 'Other'),
    ], default='walkin', string='Exchange Channel')
    exchange_line_ids = fields.One2many('pos.lite.return.wizard.exchange.line', 'wizard_id', string='New Items')
    line_ids = fields.One2many('pos.lite.return.wizard.line', 'wizard_id', string='Return Lines')

    # Computed summary
    return_total = fields.Monetary(compute='_compute_summary', string='Return Total')
    exchange_total = fields.Monetary(compute='_compute_summary', string='Exchange Total')
    exchange_difference = fields.Monetary(compute='_compute_summary', string='Difference')
    is_customer_pays = fields.Boolean(compute='_compute_summary', string='Customer Pays Extra')
    is_customer_gets_refund = fields.Boolean(compute='_compute_summary', string='Customer Gets Refunded')

    @api.depends('line_ids.qty', 'line_ids.price_unit', 'line_ids.discount', 'line_ids.discount_type',
                 'exchange_line_ids.qty', 'exchange_line_ids.price_unit',
                 'exchange_line_ids.discount', 'exchange_line_ids.discount_type',
                 'is_exchange')
    def _compute_summary(self):
        for wizard in self:
            ret = 0.0
            for line in wizard.line_ids:
                price = line.price_unit
                if line.discount_type == 'fixed':
                    price = max(price - line.discount, 0.0)
                else:
                    price = price * (1.0 - (line.discount or 0.0) / 100.0)
                ret += price * line.qty
            ex = 0.0
            for line in wizard.exchange_line_ids:
                price = line.price_unit
                if line.discount_type == 'fixed':
                    price = max(price - line.discount, 0.0)
                else:
                    price = price * (1.0 - (line.discount or 0.0) / 100.0)
                ex += price * line.qty

            wizard.return_total = ret
            wizard.exchange_total = ex if wizard.is_exchange else 0.0
            diff = ex - ret
            wizard.exchange_difference = diff
            wizard.is_customer_pays = diff > 0.01
            wizard.is_customer_gets_refund = diff < -0.01

    @api.onchange('order_id')
    def _onchange_order_id(self):
        if not self.order_id:
            self.line_ids = [(5, 0, 0)]
            return
        config = self.env['pos.lite.config'].get_default_config(self.order_id.company_id)
        self.exchange_warehouse_id = self.order_id.warehouse_id
        self.exchange_partner_id = self.order_id.partner_id
        self.exchange_channel = self.order_id.channel
        if not self.refund_journal_id:
            if config and config.journal_id:
                self.refund_journal_id = config.journal_id
            else:
                default_journal = self.order_id._get_default_payment_journal()
                if default_journal:
                    self.refund_journal_id = default_journal.id
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
                'discount_type': line.discount_type,
            }))
        self.line_ids = lines

    @api.onchange('refund_payment_method')
    def _onchange_refund_payment_method(self):
        if self.refund_payment_method and not self.refund_journal_id:
            config = self.env['pos.lite.config'].get_default_config(self.company_id)
            if config and config.journal_id:
                self.refund_journal_id = config.journal_id

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
        line_commands = [(0, 0, {
            'returned_from_line_id': l.order_line_id.id,
            'product_id': l.product_id.id,
            'description': l.description or l.product_id.display_name,
            'qty': l.qty,
            'price_unit': l.price_unit,
            'discount': l.discount,
        }) for l in self.line_ids.filtered(lambda l: l.qty > 0)]

        # 1. Create Return Order (always)
        return_note = '\n'.join([
            t for t in [
                order.note,
                self.return_reason and _('Return reason: %s') % self.return_reason,
                self.is_exchange and _('Exchange for %s') % order.name,
            ] if t
        ])
        return_order = self.env['pos.lite.order'].create({
            'company_id': order.company_id.id,
            'channel': order.channel,
            'customer_name': order.customer_name,
            'partner_id': order.partner_id.id if order.partner_id else False,
            'partner_phone': order.partner_phone,
            'partner_invoice_id': order.partner_invoice_id.id if order.partner_invoice_id else False,
            'partner_shipping_id': order.partner_shipping_id.id if order.partner_shipping_id else False,
            'partner_tax_id': order.partner_tax_id,
            'warehouse_id': order.warehouse_id.id,
            'pricelist_id': order.pricelist_id.id,
            'note': return_note,
            'is_return': True,
            'return_of_order_id': order.id,
            'return_reason': self.return_reason,
            'line_ids': line_commands,
        })

        # Refund payment (use selected method instead of hardcoded 'cash')
        refund_journal = self.refund_journal_id or return_order._get_default_payment_journal()
        refund_amount = return_order.amount_total
        self.env['pos.lite.payment'].create({
            'order_id': return_order.id,
            'payment_method': self.refund_payment_method,
            'amount': -refund_amount,
            'journal_id': refund_journal.id if refund_journal else False,
            'note': self.return_reason or _('Customer return refund'),
        })
        return_order.action_process_order()

        # 2. Exchange: create new sale order
        if self.is_exchange and self.exchange_line_ids:
            exchange_line_commands = [(0, 0, {
                'product_id': ex.product_id.id,
                'description': ex.product_id.display_name,
                'qty': ex.qty,
                'price_unit': ex.price_unit,
                'discount': ex.discount,
                'discount_type': ex.discount_type,
            }) for ex in self.exchange_line_ids]
            partner = self.exchange_partner_id or order.partner_id
            exchange_order = self.env['pos.lite.order'].create({
                'company_id': order.company_id.id,
                'channel': self.exchange_channel or order.channel,
                'customer_name': partner.name if partner else order.customer_name,
                'partner_id': partner.id if partner else False,
                'partner_phone': (partner.phone or partner.mobile) if partner else order.partner_phone,
                'partner_invoice_id': order.partner_invoice_id.id if order.partner_invoice_id else False,
                'partner_shipping_id': order.partner_shipping_id.id if order.partner_shipping_id else False,
                'partner_tax_id': partner.vat if partner else order.partner_tax_id,
                'warehouse_id': (self.exchange_warehouse_id or order.warehouse_id).id,
                'pricelist_id': order.pricelist_id.id,
                'note': _('Exchange for order %s (return: %s)') % (order.name, return_order.name),
                'is_exchange': True,
                'exchange_of_order_id': order.id,
                'line_ids': exchange_line_commands,
            })

            # Pay the full exchange order amount (full invoice + full payment is correct accounting)
            ex_journal = exchange_order._get_default_payment_journal()
            self.env['pos.lite.payment'].create({
                'order_id': exchange_order.id,
                'payment_method': self.refund_payment_method,
                'amount': exchange_order.amount_total,
                'journal_id': ex_journal.id if ex_journal else False,
                'note': _('Exchange payment for %s') % order.name,
            })
            exchange_order.action_process_order()

            return {
                'type': 'ir.actions.act_window',
                'name': _('Exchange Order'),
                'res_model': 'pos.lite.order',
                'view_mode': 'form',
                'res_id': exchange_order.id,
                'target': 'current',
            }

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
    company_id = fields.Many2one(related='wizard_id.company_id', readonly=True)
    currency_id = fields.Many2one(related='wizard_id.currency_id', readonly=True)
    order_line_id = fields.Many2one('pos.lite.order.line', required=True, readonly=True)
    product_id = fields.Many2one('product.product', required=True, readonly=True)
    description = fields.Char(readonly=True)
    qty_available = fields.Float(readonly=True)
    qty = fields.Float(default=1.0)
    price_unit = fields.Monetary(required=True)
    discount = fields.Float(default=0.0)
    discount_type = fields.Selection([
        ('percent', 'Percent'),
        ('fixed', 'Fixed'),
    ], default='percent', string='Discount Type')

    @api.constrains('qty')
    def _check_qty(self):
        for line in self:
            if line.qty <= 0:
                raise ValidationError(_('Return quantity must be greater than zero.'))
            if line.qty > line.qty_available:
                raise ValidationError(_('Return quantity cannot exceed the available quantity.'))


class PosLiteReturnWizardExchangeLine(models.TransientModel):
    _name = 'pos.lite.return.wizard.exchange.line'
    _description = 'POS Lite Exchange New Item Line'

    wizard_id = fields.Many2one('pos.lite.return.wizard', required=True, ondelete='cascade')
    company_id = fields.Many2one(related='wizard_id.company_id', readonly=True)
    currency_id = fields.Many2one(related='wizard_id.currency_id', readonly=True)
    product_id = fields.Many2one(
        'product.product', required=True,
        domain="[('sale_ok', '=', True)]",
        context="{'pos_lite_search': 1}",
        check_company=True,
    )
    description = fields.Char()
    qty = fields.Float(default=1.0)
    price_unit = fields.Monetary(required=True)
    discount = fields.Float(default=0.0)
    discount_type = fields.Selection([
        ('percent', 'Percent'),
        ('fixed', 'Fixed'),
    ], default='percent', string='Discount Type')

    @api.onchange('product_id', 'qty')
    def _onchange_product_id(self):
        if not self.product_id:
            self.description = False
            return
        self.description = self.product_id.display_name
        self.qty = self.qty or 1.0
        pricelist = self.wizard_id.order_id.pricelist_id
        partner = self.wizard_id.exchange_partner_id or self.wizard_id.order_id.partner_id
        price = self.product_id.lst_price
        if pricelist:
            try:
                if hasattr(pricelist, '_get_product_price'):
                    price = pricelist._get_product_price(self.product_id, self.qty or 1.0, partner)
                else:
                    price = pricelist._get_product_price_rule(self.product_id, self.qty or 1.0, partner)[0]
            except (AttributeError, IndexError, TypeError):
                price = self.product_id.lst_price
        self.price_unit = price

    @api.constrains('qty')
    def _check_qty(self):
        for line in self:
            if line.qty <= 0:
                raise ValidationError(_('Exchange quantity must be greater than zero.'))