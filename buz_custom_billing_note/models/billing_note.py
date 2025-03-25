from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class BillingNote(models.Model):
    _name = 'billing.note'
    _description = 'Billing Note'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    name = fields.Char(string='Number', readonly=True, copy=False, default='/')
    note_type = fields.Selection([
        ('receivable', 'Customer Invoice'),
        ('payable', 'Vendor Bill')
    ], string='Type', required=True, default='receivable', tracking=True)

    partner_id = fields.Many2one('res.partner', string='Partner', required=True, tracking=True)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today, tracking=True)
    due_date = fields.Date(string='Due Date', required=True, default=fields.Date.context_today, tracking=True)
    invoice_ids = fields.Many2many('account.move', string='Documents', tracking=True)
    amount_total = fields.Monetary(string='Total Amount', compute='_compute_amount_total', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirmed'),
        ('done', 'Done'),
        ('cancel', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', related='company_id.currency_id')
    line_ids = fields.One2many('billing.note.line', 'billing_note_id', string='Lines')
    
    # Fields for partial payment
    amount_paid = fields.Monetary(string='Amount Paid', compute='_compute_amount_paid', store=True)
    amount_residual = fields.Monetary(string='Amount Due', compute='_compute_amount_paid', store=True)
    payment_state = fields.Selection([
        ('not_paid', 'Not Paid'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('reversed', 'Reversed')
    ], string='Payment Status', compute='_compute_payment_state', store=True)
    payment_line_ids = fields.One2many('billing.note.payment', 'billing_note_id', string='Payments')
    
    # Fields for notification
    notification_sent = fields.Boolean(string='Notification Sent', default=False)
    days_before_due = fields.Integer(string='Days Before Due for Notification', default=7)

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Billing Note number must be unique per company!')
    ]

    @api.depends('invoice_ids', 'invoice_ids.amount_total')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.invoice_ids.mapped('amount_total'))

    @api.depends('amount_total', 'payment_line_ids.amount')
    def _compute_amount_paid(self):
        for rec in self:
            rec.amount_paid = sum(rec.payment_line_ids.mapped('amount'))
            rec.amount_residual = rec.amount_total - rec.amount_paid

    @api.depends('amount_total', 'amount_paid')
    def _compute_payment_state(self):
        for rec in self:
            if rec.amount_paid <= 0:
                rec.payment_state = 'not_paid'
            elif rec.amount_paid >= rec.amount_total:
                rec.payment_state = 'paid'
            else:
                rec.payment_state = 'partial'

    @api.onchange('note_type')
    def _onchange_note_type(self):
        self.invoice_ids = False
        self.partner_id = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.invoice_ids = False

    @api.constrains('date', 'due_date')
    def _check_dates(self):
        for record in self:
            if record.due_date < record.date:
                raise ValidationError(_('Due date must be greater than or equal to the billing date.'))

    def action_add_invoices(self):
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Please select a partner first.'))

        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid'),
            ('id', 'not in', self.invoice_ids.ids)
        ]

        if self.note_type == 'receivable':
            domain.append(('move_type', '=', 'out_invoice'))
            view_id = self.env.ref('account.view_out_invoice_tree').id
        else:
            domain.append(('move_type', '=', 'in_invoice'))
            view_id = self.env.ref('account.view_in_invoice_tree').id

        return {
            'name': _('Select Documents'),
            'type': 'ir.actions.act_window',
            'view_mode': 'tree',
            'res_model': 'account.move',
            'views': [(view_id, 'tree')],
            'domain': domain,
            'target': 'new',
            'multi_select': True,
            'context': {
                'create': False,
                'edit': False,
                'delete': False
            }
        }

    def action_confirm(self):
        for rec in self:
            if not rec.invoice_ids:
                raise UserError(_('Please add at least one document.'))
            if rec.state == 'draft':
                if rec.name == '/':
                    if rec.note_type == 'receivable':
                        sequence_code = 'customer.billing.note'
                    else:
                        sequence_code = 'vendor.billing.note'
                    rec.name = self.env['ir.sequence'].next_by_code(sequence_code)
                rec.state = 'confirm'

    def action_done(self):
        for rec in self:
            if rec.state == 'confirm':
                rec.state = 'done'

    def action_cancel(self):
        for rec in self:
            if rec.state != 'done':
                rec.state = 'cancel'

    def action_draft(self):
        for rec in self:
            if rec.state == 'cancel':
                rec.state = 'draft'

    def unlink(self):
        if any(rec.state != 'draft' for rec in self):
            raise UserError(_('You can only delete draft billing notes.'))
        return super().unlink()

    def action_register_payment(self):
        self.ensure_one()
        return {
            'name': _('Register Payment'),
            'type': 'ir.actions.act_window',
            'res_model': 'billing.note.payment.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_billing_note_id': self.id,
                'default_amount': self.amount_residual,
            }
        }

    def action_view_payments(self):
        self.ensure_one()
        return {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'billing.note.payment',
            'view_mode': 'tree,form',
            'domain': [('billing_note_id', '=', self.id)],
            'context': {'default_billing_note_id': self.id}
        }

    def _check_due_date_notification(self):
        today = fields.Date.today()
        domain = [
            ('state', '=', 'confirm'),
            ('notification_sent', '=', False),
            ('payment_state', 'in', ['not_paid', 'partial']),
        ]
        billing_notes = self.search(domain)
        
        for note in billing_notes:
            days_until_due = (note.due_date - today).days
            if days_until_due <= note.days_before_due and days_until_due >= 0:
                note._send_due_date_notification()
                note.notification_sent = True

    def _send_due_date_notification(self):
        self.ensure_one()
        template = self.env.ref('buz_custom_billing_note.billing_note_due_date_template')
        if template:
            template.send_mail(self.id, force_send=True)

class BillingNoteLine(models.Model):
    _name = 'billing.note.line'
    _description = 'Billing Note Line'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note')
    name = fields.Char(string='Description')
    amount = fields.Float(string='Amount')

class BillingNotePayment(models.Model):
    _name = 'billing.note.payment'
    _description = 'Billing Note Payment'
    _order = 'payment_date desc, id desc'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True)
    name = fields.Char(string='Reference', required=True)
    amount = fields.Monetary(string='Amount', required=True)
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('check', 'Check'),
    ], string='Payment Method', required=True)
    notes = fields.Text(string='Notes')
    company_id = fields.Many2one('res.company', related='billing_note_id.company_id', store=True)
    currency_id = fields.Many2one('res.currency', related='billing_note_id.currency_id')