from dateutil.relativedelta import relativedelta

from odoo import api, fields, models


class WarrantyCardLine(models.Model):
    _name = 'warranty.card.line'
    _description = 'Warranty Card Line'
    _order = 'card_id, sequence, id'

    card_id = fields.Many2one(
        'warranty.card',
        string='Warranty Card',
        required=True,
        ondelete='cascade',
        index=True,
    )
    sequence = fields.Integer(default=10)
    partner_id = fields.Many2one(related='card_id.partner_id', store=True, index=True)
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        index=True,
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Serial/Lot Number',
        domain="[('product_id', '=', product_id)]",
    )
    product_description = fields.Char(string='Description')
    start_date = fields.Date(
        string='Start Date',
        compute='_compute_start_date',
        store=True,
        readonly=False,
        required=True,
    )
    warranty_duration = fields.Integer(string='Duration', readonly=True)
    warranty_period_unit = fields.Selection([
        ('month', 'Month(s)'),
        ('year', 'Year(s)'),
    ], string='Period Unit', readonly=True)
    end_date = fields.Date(
        string='End Date',
        compute='_compute_end_date',
        store=True,
        readonly=False,
    )
    is_expired = fields.Boolean(string='Expired', compute='_compute_expiry')
    days_remaining = fields.Integer(string='Days Remaining', compute='_compute_expiry')
    warranty_type = fields.Selection(
        related='product_id.product_tmpl_id.warranty_type',
        string='Warranty Type',
        readonly=True,
    )
    condition = fields.Text(
        related='product_id.product_tmpl_id.warranty_condition',
        string='Warranty Conditions',
        readonly=True,
    )
    product_image = fields.Image(related='product_id.image_1024', readonly=True)

    @api.depends('card_id.start_date')
    def _compute_start_date(self):
        for line in self:
            line.start_date = line.card_id.start_date or fields.Date.today()

    @api.depends('start_date', 'warranty_duration', 'warranty_period_unit')
    def _compute_end_date(self):
        for line in self:
            if line.start_date and line.warranty_duration:
                if line.warranty_period_unit == 'year':
                    delta = relativedelta(years=line.warranty_duration)
                else:
                    delta = relativedelta(months=line.warranty_duration)
                line.end_date = line.start_date + delta
            else:
                line.end_date = False

    def _compute_expiry(self):
        today = fields.Date.today()
        for line in self:
            line.is_expired = bool(line.end_date and line.end_date < today)
            line.days_remaining = max((line.end_date - today).days, 0) if line.end_date else 0

    @api.model
    def _get_product_warranty_values(self, product):
        """Snapshot the effective product warranty for a line."""
        if not product:
            return {'warranty_duration': False, 'warranty_period_unit': False}
        return product.product_tmpl_id._get_effective_warranty_period()

    @api.onchange('product_id')
    def _onchange_product_id(self):
        self.update(self._get_product_warranty_values(self.product_id))
        if self.lot_id and self.lot_id.product_id != self.product_id:
            self.lot_id = False

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('product_id') and 'warranty_duration' not in vals:
                product = self.env['product.product'].browse(vals['product_id'])
                vals.update(self._get_product_warranty_values(product))
        lines = super().create(vals_list)
        lines._trigger_dashboard_update('warranty_card_updated')
        return lines

    def write(self, vals):
        if 'product_id' in vals:
            product = self.env['product.product'].browse(vals['product_id']) if vals['product_id'] else False
            vals = dict(vals, **self._get_product_warranty_values(product))
        result = super().write(vals)
        if {'product_id', 'end_date', 'start_date'} & set(vals):
            self._trigger_dashboard_update('warranty_card_updated')
        return result

    def unlink(self):
        cards = self.card_id
        result = super().unlink()
        if cards.exists():
            self.env['warranty.dashboard.cache']._trigger_update('warranty_card_updated', cards.exists())
        return result

    def _trigger_dashboard_update(self, event):
        if self.card_id:
            self.env['warranty.dashboard.cache']._trigger_update(event, self.card_id)
