from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from datetime import date, timedelta


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
        required=False,
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
    is_expired = fields.Boolean(
        string='Is Expired',
        compute='_compute_is_expired',
        store=True
    )
    days_remaining = fields.Integer(
        string='Days Remaining',
        compute='_compute_days_remaining',
        search='_search_days_remaining'
    )
    days_since_expiry = fields.Integer(
        string='Days Since Expiry',
        compute='_compute_days_since_expiry',
        search='_search_days_since_expiry'
    )
    claim_count = fields.Integer(
        string='Claim Count',
        compute='_compute_claim_count',
        search='_search_claim_count',
    )
    last_claim_date = fields.Date(
        string='Last Claim Date',
        compute='_compute_last_claim_date',
        search='_search_last_claim_date'
    )
    product_description = fields.Char(
        string='Product Description',
        help='Additional product description for manually managed warranty cards',
    )

    dealer_name = fields.Char(string='Dealer / Shop')
    invoice_number = fields.Char(string='Invoice No.')
    proof_attachment_ids = fields.Many2many(
        'ir.attachment', 'warranty_card_proof_rel', 'card_id', 'attachment_id',
        string='Proof of Purchase')

    proof_pdf = fields.Binary(
        string='Proof of Purchase Preview',
        compute='_compute_proof_pdf',
    )
    proof_pdf_filename = fields.Char(compute='_compute_proof_pdf')
    proof_image = fields.Image(
        string='Proof of Purchase Image',
        compute='_compute_proof_image',
    )
    days_remaining_text = fields.Char(
        string='Remaining Period',
        compute='_compute_days_remaining_text',
    )

    partner_phone = fields.Char(related='partner_id.phone', string='Phone', readonly=True)
    partner_email = fields.Char(related='partner_id.email', string='Email', readonly=True)
    partner_address = fields.Char(related='partner_id.contact_address', string='Address', readonly=True)
    product_image = fields.Image(related='product_id.image_1024', string='Product Image', readonly=True)

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

    @api.depends('proof_attachment_ids', 'proof_attachment_ids.mimetype', 'proof_attachment_ids.datas')
    def _compute_proof_pdf(self):
        for record in self:
            pdf = record.proof_attachment_ids.filtered(
                lambda a: a.mimetype == 'application/pdf')[:1]
            record.proof_pdf = pdf.datas if pdf else False
            record.proof_pdf_filename = pdf.name if pdf else False

    @api.depends('proof_attachment_ids', 'proof_attachment_ids.mimetype', 'proof_attachment_ids.datas')
    def _compute_proof_image(self):
        for record in self:
            image = record.proof_attachment_ids.filtered(
                lambda a: a.mimetype and a.mimetype.startswith('image/'))[:1]
            record.proof_image = image.datas if image else False

    @api.depends('end_date')
    def _compute_days_remaining_text(self):
        today = fields.Date.today()
        for record in self:
            if record.end_date and record.end_date > today:
                delta = relativedelta(record.end_date, today)
                parts = []
                if delta.years:
                    parts.append(_('%s year(s)') % delta.years)
                if delta.months:
                    parts.append(_('%s month(s)') % delta.months)
                if delta.days:
                    parts.append(_('%s day(s)') % delta.days)
                record.days_remaining_text = _('approx. %s') % ' '.join(parts) if parts else ''
            else:
                record.days_remaining_text = ''

    @api.depends('end_date')
    def _compute_days_since_expiry(self):
        """Compute days since expiry for expired warranties"""
        today = fields.Date.today()
        for record in self:
            if record.end_date and record.end_date < today:
                record.days_since_expiry = (today - record.end_date).days
            else:
                record.days_since_expiry = 0

    def _compute_claim_count(self):
        if 'service.receipt' not in self.env.registry.models:
            self.update({'claim_count': 0})
            return
        receipt_model = self.env['service.receipt'].sudo()
        for record in self:
            record.claim_count = receipt_model.search_count([
                ('warranty_card_id', '=', record.id),
                ('service_case_type', '=', 'replacement'),
            ])

    def _compute_last_claim_date(self):
        if 'service.receipt' not in self.env.registry.models:
            self.update({'last_claim_date': False})
            return
        receipt_model = self.env['service.receipt'].sudo()
        for record in self:
            receipt = receipt_model.search([
                ('warranty_card_id', '=', record.id),
            ], order='request_date desc, id desc', limit=1)
            record.last_claim_date = receipt.request_date if receipt else False

    def action_activate(self):
        self.write({'state': 'active'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_reset_to_draft(self):
        self.write({'state': 'draft'})

    def action_print_certificate(self):
        self.ensure_one()
        return self.env.ref('buz_warranty_management.action_report_warranty_certificate').report_action(self)

    @api.model
    def create(self, vals):
        """Trigger cache update on new warranty card"""
        record = super().create(vals)
        # Trigger cache update
        self.env['warranty.dashboard.cache']._trigger_update('warranty_card_created', record)
        return record
    
    def write(self, vals):
        """Trigger cache update on warranty card changes"""
        # Check if critical fields changed
        critical_fields = ['state', 'end_date', 'partner_id', 'product_id']
        has_critical_change = any(field in vals for field in critical_fields)
        
        result = super().write(vals)
        
        if has_critical_change:
            # Trigger cache update
            self.env['warranty.dashboard.cache']._trigger_update('warranty_card_updated', self)
        
        return result
    
    def unlink(self):
        """Trigger cache update on warranty card deletion"""
        # Trigger cache update before deletion
        self.env['warranty.dashboard.cache']._trigger_update('warranty_card_deleted', self)
        return super().unlink()

    def _search_claim_count(self, operator, value):
        if 'service.receipt' not in self.env.registry.models:
            return [('id', '=', 0)]
        cards = self.search([]).filtered(
            lambda card: card.claim_count > value if operator in ('>', '>=')
            else card.claim_count < value if operator in ('<', '<=')
            else card.claim_count == value
        )
        return [('id', 'in', cards.ids)]

    def _search_last_claim_date(self, operator, value):
        if 'service.receipt' not in self.env.registry.models:
            return [('id', '=', 0)]
        receipt_model = self.env['service.receipt'].sudo()
        receipts = receipt_model.search([('request_date', operator, value)])
        return [('id', 'in', receipts.mapped('warranty_card_id').ids)]

    @api.model
    def cron_update_expired_warranties(self):
        today = fields.Date.today()
        active_warranties = self.search([
            ('state', '=', 'active'),
            ('end_date', '<', today)
        ])
        
        if active_warranties:
            active_warranties.write({'state': 'expired'})
            # Trigger cache update for batch operation
            self.env['warranty.dashboard.cache']._trigger_update('warranty_cards_expired')
        
        return True

    @api.model
    def _search_days_remaining(self, operator, value):
        """Search method for days_remaining field"""
        # Search warranty cards with specific days remaining
        today = fields.Date.today()
        if operator in ('=', '!=', '>', '>=', '<', '<='):
            if operator == '=':
                target_start = today + timedelta(days=value)
                target_end = today + timedelta(days=value+1)
                return [('end_date', '>=', today), ('end_date', '<', target_start)]
            elif operator == '>':
                target_date = today + timedelta(days=value)
                return [('end_date', '>', target_date)]
            elif operator == '>=':
                target_date = today + timedelta(days=value)
                return [('end_date', '>=', target_date)]
            elif operator == '<':
                target_date = today + timedelta(days=value)
                return [('end_date', '>=', today), ('end_date', '<', target_date)]
            elif operator == '<=':
                target_date = today + timedelta(days=value)
                return [('end_date', '<=', target_date)]
            elif operator == '!=':
                target_start = today + timedelta(days=value)
                target_end = today + timedelta(days=value+1)
                return ['|', ('end_date', '<', today), ('end_date', '>=', target_start)]
        return [('id', '=', False)]

    @api.model
    def _search_days_since_expiry(self, operator, value):
        """Search method for days_since_expiry field"""
        # Search warranty cards with specific days since expiry
        today = fields.Date.today()
        if operator in ('=', '!=', '>', '>=', '<', '<='):
            if operator == '=':
                target_start = today - timedelta(days=value)
                target_end = today - timedelta(days=value-1)
                return [('end_date', '<', today), ('end_date', '>=', target_start), ('end_date', '<', target_end)]
            elif operator == '>':
                target_date = today - timedelta(days=value)
                return [('end_date', '<', target_date)]
            elif operator == '>=':
                target_date = today - timedelta(days=value)
                return [('end_date', '<=', target_date)]
            elif operator == '<':
                target_date = today - timedelta(days=value)
                return [('end_date', '>=', target_date)]
            elif operator == '<=':
                target_date = today - timedelta(days=value)
                return [('end_date', '>=', target_date)]
            elif operator == '!=':
                target_start = today - timedelta(days=value)
                target_end = today - timedelta(days=value-1)
                return ['|', ('end_date', '>=', today), ('end_date', '<', target_start), ('end_date', '>=', target_end)]
        return [('id', '=', False)]
