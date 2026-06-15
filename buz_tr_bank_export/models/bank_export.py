from odoo import models, fields, api, _

class BuzTrBankExport(models.Model):
    _name = 'buz.tr.bank.export'
    _description = 'Document of transfer money abroad'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Document No.', required=True, copy=False, readonly=True, default=lambda self: _('New'), tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, default='draft', tracking=True)
    
    transfer_date = fields.Date(string='Transfer date', required=True, default=fields.Date.context_today)
    vendor_id = fields.Many2one('res.partner', string='Pay to', required=True, tracking=True)
    destination_bank = fields.Char(string='Destination Bank')
    account_no = fields.Char(string='Account No.')
    attn = fields.Char(string='Attn')
    refer_to = fields.Char(string='Refer to')
    trading_conditions = fields.Char(string='Trading conditions')
    type_of_goods = fields.Char(string='Type of goods')
    arrival_date = fields.Date(string='Arrival date')
    terms_of_payment = fields.Char(string='Terms of payment')
    
    currency_id = fields.Many2one('res.currency', string='Currency', required=True, default=lambda self: self.env.company.currency_id)
    company_id = fields.Many2one('res.company', string='Company', required=True, default=lambda self: self.env.company)
    
    line_ids = fields.One2many('buz.tr.bank.export.line', 'export_id', string='Lines')
    
    total_amount = fields.Monetary(string='Total', compute='_compute_totals', store=True)
    add_reduce_amount = fields.Monetary(string='Add/Reduce')
    grand_total_amount = fields.Monetary(string='Grand total Amount', compute='_compute_totals', store=True)
    amount_text = fields.Char(string='Amount in Words', compute='_compute_amount_text')
    
    remark = fields.Text(string='Remark')
    
    payment_id = fields.Many2one('account.payment', string='Vendor Payment', readonly=True, copy=False)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('buz.tr.bank.export') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.transfer_amount', 'add_reduce_amount')
    def _compute_totals(self):
        for record in self:
            total = sum(record.line_ids.mapped('transfer_amount'))
            record.total_amount = total
            record.grand_total_amount = total + record.add_reduce_amount

    @api.depends('grand_total_amount', 'currency_id')
    def _compute_amount_text(self):
        for record in self:
            if record.currency_id:
                record.amount_text = record.currency_id.amount_to_text(record.grand_total_amount)
            else:
                record.amount_text = False

    def action_confirm(self):
        for record in self:
            if record.state != 'draft':
                continue
            record.state = 'confirmed'

    def action_cancel(self):
        for record in self:
            if record.payment_id and record.payment_id.state != 'cancel':
                raise UserError(_("You cannot cancel this document because the associated payment is not cancelled. Please cancel the payment first."))
            record.state = 'cancel'

    def action_draft(self):
        for record in self:
            record.state = 'draft'

    def action_done(self):
        for record in self:
            if record.state != 'confirmed':
                continue
            record.state = 'done'


class BuzTrBankExportLine(models.Model):
    _name = 'buz.tr.bank.export.line'
    _description = 'Bank Export Line'

    export_id = fields.Many2one('buz.tr.bank.export', string='Export Reference', required=True, ondelete='cascade')
    sequence = fields.Integer(string='No.', default=10)
    lot_no = fields.Char(string='Lot No.')
    import_date = fields.Date(string='Import date')
    etd_date = fields.Date(string='ETDDATE')
    purchase_id = fields.Many2one('purchase.order', string='PO No.', domain=[('state', '!=', 'cancel')])
    po_ref = fields.Char(string='Ref.No.', related='purchase_id.partner_ref', store=True, readonly=False)
    po_amount = fields.Monetary(string='PO Amount', related='purchase_id.amount_total', store=True, readonly=False)
    currency_id = fields.Many2one(related='export_id.currency_id', depends=['export_id.currency_id'], store=True)
    transfer_amount = fields.Monetary(string='Transfer Amount')

    @api.onchange('purchase_id')
    def _onchange_purchase_id(self):
        if self.purchase_id:
            self.transfer_amount = self.purchase_id.amount_total


