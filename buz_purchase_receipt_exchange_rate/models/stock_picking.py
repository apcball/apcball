# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    exchange_rate_date = fields.Date(
        string="Exchange Rate Date",
        copy=False,
        tracking=True,
    )
    exchange_rate = fields.Float(
        string="Exchange Rate",
        digits=(16, 6),
        copy=False,
        tracking=True,
        help="Company currency per 1 unit of foreign currency, e.g. 32.85 THB/USD.",
    )
    exchange_rate_source = fields.Selection(
        [
            ('odoo', 'Odoo Currency Rate'),
            ('manual', 'Manual'),
        ],
        string="Exchange Rate Source",
        default='odoo',
        copy=False,
        tracking=True,
    )
    actual_rate_date = fields.Date(
        string="Actual Rate Used Date",
        copy=False,
        readonly=True,
        help="Date of the Odoo currency rate actually found, which may differ "
             "from the requested Exchange Rate Date if no rate exists on that day.",
    )
    original_exchange_rate = fields.Float(
        string="Original Exchange Rate",
        digits=(16, 6),
        copy=False,
        readonly=True,
        help="Rate first fetched via 'Get Exchange Rate', kept for audit even "
             "if later overridden manually.",
    )
    original_exchange_rate_date = fields.Date(
        string="Original Exchange Rate Date",
        copy=False,
        readonly=True,
    )

    purchase_currency_id = fields.Many2one(
        'res.currency',
        string="Purchase Currency",
        compute='_compute_purchase_currency_id',
    )
    is_foreign_currency_receipt = fields.Boolean(
        string="Is Foreign Currency Receipt",
        compute='_compute_purchase_currency_id',
    )
    foreign_total_amount = fields.Monetary(
        string="Total Foreign Amount",
        compute='_compute_estimated_cost',
        currency_field='purchase_currency_id',
    )
    estimated_cost = fields.Monetary(
        string="Estimated Cost",
        compute='_compute_estimated_cost',
        currency_field='company_currency_id',
    )
    company_currency_id = fields.Many2one(
        related='company_id.currency_id',
        string="Company Currency",
    )

    @api.depends('move_ids.purchase_line_id', 'picking_type_id.code')
    def _compute_purchase_currency_id(self):
        for picking in self:
            po_lines = picking.move_ids.purchase_line_id
            currencies = po_lines.currency_id
            # A receipt is expected to carry a single PO currency; if moves
            # from different-currency POs were ever merged onto one picking,
            # fall back to no currency rather than guessing - button_validate
            # will then simply not apply this module's logic to that receipt.
            currency = currencies if len(currencies) == 1 else self.env['res.currency']
            picking.purchase_currency_id = currency
            picking.is_foreign_currency_receipt = bool(
                picking.picking_type_id.code == 'incoming'
                and currency
                and currency != picking.company_id.currency_id
            )

    @api.depends(
        'is_foreign_currency_receipt', 'exchange_rate',
        'move_ids.product_qty', 'move_ids.quantity', 'move_ids.purchase_line_id.price_unit',
        'move_ids.purchase_line_id.discount', 'move_ids.purchase_line_id.taxes_id',
    )
    def _compute_estimated_cost(self):
        for picking in self:
            picking.foreign_total_amount = 0.0
            picking.estimated_cost = 0.0
            if not picking.is_foreign_currency_receipt:
                continue
            foreign_total = 0.0
            for move in picking.move_ids.filtered(lambda m: m.purchase_line_id):
                line = move.purchase_line_id
                # Before Validate, quantity done isn't final yet - preview
                # against the demanded quantity. Once moves are done, use
                # what was actually received so a partial receipt's preview
                # matches what it actually valued.
                qty = move.quantity if move.state == 'done' else move.product_qty
                qty_in_po_uom = move.product_uom._compute_quantity(
                    qty, line.product_uom, rounding_method='HALF-UP')
                foreign_total += line._get_gross_price_unit() * qty_in_po_uom
            picking.foreign_total_amount = foreign_total
            if picking.exchange_rate > 0:
                picking.estimated_cost = foreign_total * picking.exchange_rate

    def _get_odoo_rate(self, rate_date):
        """Return (rate, actual_date) where rate is company-currency-per-1-foreign-unit
        at rate_date, falling back to the latest rate before that date, mirroring
        Odoo's own res.currency.rate lookup behavior.
        """
        self.ensure_one()
        currency = self.purchase_currency_id
        company = self.company_id
        company_currency = company.currency_id
        if not currency or currency == company_currency:
            return 0.0, rate_date
        rate_record = self.env['res.currency.rate'].search([
            ('currency_id', '=', currency.id),
            ('name', '<=', rate_date),
            ('company_id', 'in', [company.id, False]),
        ], order='name desc', limit=1)
        actual_date = rate_record.name if rate_record else rate_date
        # rate = company_currency amount per 1 foreign unit
        rate = currency._convert(1.0, company_currency, company, actual_date, round=False)
        return rate, actual_date

    def action_get_exchange_rate(self):
        self.ensure_one()
        if not self.is_foreign_currency_receipt:
            raise UserError(_("This Receipt is not a foreign currency purchase receipt."))
        if not self.exchange_rate_date:
            raise UserError(_("Please set an Exchange Rate Date first."))
        rate, actual_date = self._get_odoo_rate(self.exchange_rate_date)
        if not rate:
            raise UserError(_("No currency rate found for %s.", self.purchase_currency_id.name))
        self.exchange_rate = rate
        self.exchange_rate_source = 'odoo'
        self.actual_rate_date = actual_date
        if not self.original_exchange_rate:
            self.original_exchange_rate = rate
            self.original_exchange_rate_date = actual_date
        if actual_date != self.exchange_rate_date:
            self.message_post(body=_(
                "Requested Rate Date: %(requested)s. Actual Rate Used: %(actual)s (Rate: %(rate)s).",
                requested=self.exchange_rate_date,
                actual=actual_date,
                rate=rate,
            ))
        return True

    def action_recalculate_cost(self):
        self.ensure_one()
        if not self.is_foreign_currency_receipt:
            raise UserError(_("This Receipt is not a foreign currency purchase receipt."))
        if self.exchange_rate <= 0:
            raise UserError(_("Please set a valid Exchange Rate first."))
        self._compute_estimated_cost()
        return True

    @api.onchange('exchange_rate')
    def _onchange_exchange_rate_set_manual(self):
        for picking in self:
            if picking.exchange_rate:
                picking.exchange_rate_source = 'manual'

    @api.constrains('exchange_rate')
    def _check_exchange_rate_positive(self):
        for picking in self:
            if picking.exchange_rate and picking.exchange_rate <= 0:
                raise ValidationError(_("Exchange Rate must be greater than 0."))

    def button_validate(self):
        for picking in self:
            if picking.is_foreign_currency_receipt:
                if not picking.exchange_rate_date:
                    raise UserError(_(
                        "กรุณาระบุ Exchange Rate Date ก่อน Validate Receipt (%s).", picking.name))
                if picking.exchange_rate <= 0:
                    raise UserError(_(
                        "กรุณาระบุ Exchange Rate ก่อน Validate Receipt (%s).", picking.name))
        return super().button_validate()

    def _action_done(self):
        for picking in self:
            eligible_moves = picking.move_ids.filtered(lambda m: m._use_receipt_exchange_rate())
            for move in eligible_moves:
                move.custom_cost_price = move._get_price_unit()
                move.use_custom_cost = True
        return super()._action_done()
