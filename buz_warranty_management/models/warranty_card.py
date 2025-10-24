from odoo import models, fields, api
from dateutil.relativedelta import relativedelta
from datetime import date


class WarrantyCard(models.Model):
    _name = 'warranty.card'
    _description = 'Warranty Card'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='Warranty Number',
        required=True,
        readonly=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('warranty.card') or 'New',
        copy=False,
        tracking=True
    )
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True
    )
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        tracking=True
    )
    lot_id = fields.Many2one(
        'stock.lot',
        string='Serial/Lot Number',
        tracking=True
    )
    start_date = fields.Date(
        string='Warranty Start Date',
        required=True,
        default=fields.Date.today,
        tracking=True
    )
    end_date = fields.Date(
        string='Warranty End Date',
        compute='_compute_end_date',
        store=True,
        readonly=False,
        tracking=True
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sale Order',
        tracking=True
    )
    picking_id = fields.Many2one(
        'stock.picking',
        string='Delivery Order',
        tracking=True
    )
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    condition = fields.Text(
        string='Warranty Conditions',
        related='product_id.product_tmpl_id.warranty_condition',
        readonly=True
    )
    warranty_type = fields.Selection(
        string='Warranty Type',
        related='product_id.product_tmpl_id.warranty_type',
        readonly=True
    )
    warranty_duration = fields.Integer(
        string='Duration',
        related='product_id.product_tmpl_id.warranty_duration',
        readonly=True
    )
    warranty_period_unit = fields.Selection(
        string='Period Unit',
        related='product_id.product_tmpl_id.warranty_period_unit',
        readonly=True
    )
    claim_ids = fields.One2many(
        'warranty.claim',
        'warranty_card_id',
        string='Claims'
    )
    claim_count = fields.Integer(
        string='Claim Count',
        compute='_compute_claim_count'
    )
    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
        store=True
    )
    days_remaining = fields.Integer(
        string='Days Remaining',
        compute='_compute_days_remaining'
    )

    @api.depends('start_date', 'product_id.product_tmpl_id.warranty_duration', 'product_id.product_tmpl_id.warranty_period_unit')
    def _compute_end_date(self):
        for record in self:
            if record.start_date:
                if record.product_id and record.product_id.product_tmpl_id.warranty_duration:
                    duration = record.product_id.product_tmpl_id.warranty_duration
                    unit = record.product_id.product_tmpl_id.warranty_period_unit or 'month'
                    
                    if unit == 'year':
                        record.end_date = record.start_date + relativedelta(years=duration)
                    else:  # month
                        record.end_date = record.start_date + relativedelta(months=duration)
                else:
                    # Default to 12 months if no duration specified
                    record.end_date = record.start_date + relativedelta(months=12)
            else:
                record.end_date = False

    @api.depends('claim_ids')
    def _compute_claim_count(self):
        for record in self:
            record.claim_count = len(record.claim_ids)

    @api.depends('end_date')
    def _compute_is_expired(self):
        today = fields.Date.today()
        for record in self:
            record.is_expired = record.end_date and record.end_date < today

    @api.depends('end_date')
    def _compute_days_remaining(self):
        today = fields.Date.today()
        for record in self:
            if record.end_date:
                delta = (record.end_date - today).days
                record.days_remaining = delta if delta > 0 else 0
            else:
                record.days_remaining = 0

    def action_activate(self):
        self.write({'state': 'active'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_view_claims(self):
        self.ensure_one()
        action = self.env.ref('buz_warranty_management.action_warranty_claim').read()[0]
        action['domain'] = [('warranty_card_id', '=', self.id)]
        action['context'] = {'default_warranty_card_id': self.id}
        return action

    def action_print_certificate(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_report_warranty_certificate').report_action(self)

    @api.model
    def cron_update_expired_warranties(self):
        today = fields.Date.today()
        active_warranties = self.search([
            ('state', '=', 'active'),
            ('end_date', '<', today)
        ])
        active_warranties.write({'state': 'expired'})
        return True
