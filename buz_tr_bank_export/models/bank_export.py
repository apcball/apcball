from odoo import models, fields, api, _
from odoo.exceptions import UserError

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
            
            invoices = record.line_ids.mapped('invoice_id')
            if not invoices:
                raise UserError(_("Please select at least one invoice in the lines to register payment."))
            
            record.state = 'confirmed'
            
            # Call the standard register payment wizard
            action = invoices.action_register_payment()
            
            # Inject context to link the payment back to this document
            context = action.get('context', {})
            if isinstance(context, str):
                # evaluate string context if necessary, but action_register_payment usually returns a dict context
                pass
            
            action['context'] = dict(
                self.env.context,
                active_ids=invoices.ids,
                active_model='account.move',
                buz_export_id=record.id,
                default_amount=record.grand_total_amount, # Pre-fill amount with our grand total
                default_communication=record.name
            )
            return action

    def action_cancel(self):
        for record in self:
            if record.payment_id and record.payment_id.state != 'cancel':
                raise UserError(_("You cannot cancel this document because the associated payment is not cancelled. Please cancel the payment first."))
            record.state = 'cancel'

    def action_draft(self):
        for record in self:
            record.state = 'draft'


class BuzTrBankExportLine(models.Model):
    _name = 'buz.tr.bank.export.line'
    _description = 'Bank Export Line'

    export_id = fields.Many2one('buz.tr.bank.export', string='Export Reference', required=True, ondelete='cascade')
    sequence = fields.Integer(string='No.', default=10)
    lot_no = fields.Char(string='Lot No.')
    import_date = fields.Date(string='Import date')
    etd_date = fields.Date(string='ETDDATE')
    invoice_id = fields.Many2one('account.move', string='Invoice No.', domain=[('move_type', 'in', ('in_invoice', 'in_receipt'))])
    ref_no = fields.Char(string='Ref.No.', related='invoice_id.ref', store=True, readonly=False)
    currency_id = fields.Many2one(related='export_id.currency_id', depends=['export_id.currency_id'], store=True)
    amount = fields.Monetary(string='Amount', related='invoice_id.amount_total', store=True, readonly=False)
    transfer_amount = fields.Monetary(string='Transfer Amount')

    @api.onchange('invoice_id')
    def _onchange_invoice_id(self):
        if self.invoice_id:
            self.transfer_amount = self.invoice_id.amount_residual

class AccountPaymentRegister(models.TransientModel):
    _inherit = 'account.payment.register'

    def _create_payments(self):
        payments = super()._create_payments()
        buz_export_id = self.env.context.get('buz_export_id')
        if buz_export_id:
            export_doc = self.env['buz.tr.bank.export'].browse(buz_export_id)
            if export_doc and payments:
                export_doc.payment_id = payments[0].id
        return payments
