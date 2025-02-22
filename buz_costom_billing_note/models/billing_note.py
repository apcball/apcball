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

    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Billing Note number must be unique per company!')
    ]

    @api.depends('invoice_ids')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.invoice_ids.mapped('amount_total'))

    @api.onchange('note_type')
    def _onchange_note_type(self):
        self.invoice_ids = False
        self.partner_id = False

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        self.invoice_ids = False

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

class BillingNoteLine(models.Model):
    _name = 'billing.note.line'
    _description = 'Billing Note Line'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note')
    name = fields.Char(string='Description')
    amount = fields.Float(string='Amount')