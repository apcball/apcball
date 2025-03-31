from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

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
    
    # Fields for documents
    invoice_ids = fields.Many2many(
        'account.move', 'billing_note_invoice_rel',
        'billing_note_id', 'invoice_id',
        string='Documents',
        domain="[('id', 'in', available_invoice_ids)]",
        tracking=True
    )
    available_invoice_ids = fields.Many2many(
        'account.move', 'billing_note_available_invoice_rel',
        'billing_note_id', 'invoice_id',
        string='Available Invoices',
        compute='_compute_available_invoices',
        store=True
    )
    
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

    # Fields for tracking dates
    messenger_sent_date = fields.Date(string='วันที่ส่งแมสเซนเจอร์', tracking=True)
    messenger_received_date = fields.Date(string='วันที่รับจากแมสเซนเจอร์', tracking=True)
    ar_sent_date = fields.Date(string='วันที่ส่งบัญชีลูกหนี้', tracking=True)
    ar_received_date = fields.Date(string='วันที่บัญชีลูกหนี้รับ', tracking=True)
    expected_payment_date = fields.Date(string='วันที่คาดว่าจะได้รับเงิน', tracking=True)
    note = fields.Text(string='หมายเหตุ', tracking=True)

    # Fields for tracking billing status in invoices
    available_invoice_ids = fields.Many2many(
        'account.move', 'billing_note_available_invoice_rel',
        'billing_note_id', 'invoice_id',
        string='Available Invoices',
        compute='_compute_available_invoices',
        store=True
    )

    @api.depends('partner_id', 'note_type', 'state')
    def _compute_available_invoices(self):
        """Compute available invoices that can be added to billing note"""
        for record in self:
            if not record.partner_id or record.state not in ['draft']:
                record.available_invoice_ids = [(5, 0, 0)]
                continue

            domain = [
                ('partner_id', '=', record.partner_id.id),
                ('state', '=', 'posted'),
                ('payment_state', '!=', 'paid'),
                ('amount_residual', '>', 0.0),
            ]

            if record.note_type == 'receivable':
                domain.append(('move_type', '=', 'out_invoice'))
            else:
                domain.append(('move_type', '=', 'in_invoice'))

            # Get all confirmed billing notes except current one (if it exists in DB)
            if not record._origin or not record._origin.id:
                confirmed_notes_domain = [('state', 'in', ['confirm', 'done'])]
            else:
                confirmed_notes_domain = [
                    ('state', 'in', ['confirm', 'done']),
                    ('id', '!=', record._origin.id)
                ]

            confirmed_billing_notes = self.search(confirmed_notes_domain)
            billed_invoice_ids = confirmed_billing_notes.mapped('invoice_ids').ids

            # Exclude already billed invoices from domain
            if billed_invoice_ids:
                domain.append(('id', 'not in', billed_invoice_ids))

            # Exclude currently selected invoices if any
            if record.invoice_ids:
                domain.append(('id', 'not in', record.invoice_ids.ids))

            available_invoices = self.env['account.move'].search(domain)
            record.available_invoice_ids = [(6, 0, available_invoices.ids)]

    @api.constrains('invoice_ids')
    def _check_duplicate_invoices(self):
        """Check for duplicate invoices across billing notes"""
        for record in self:
            if record.invoice_ids:
                # Get all other billing notes
                other_billing_notes = self.search([
                    ('id', '!=', record.id),
                    ('state', 'in', ['draft', 'confirm', 'done'])
                ])
                
                # Check each invoice
                for invoice in record.invoice_ids:
                    duplicate_notes = other_billing_notes.filtered(
                        lambda bn: invoice in bn.invoice_ids
                    )
                    if duplicate_notes:
                        raise ValidationError(_(
                            'Invoice %(invoice)s is already included in billing note(s): %(notes)s'
                        ) % {
                            'invoice': invoice.name,
                            'notes': ', '.join(duplicate_notes.mapped('name'))
                        })

    @api.onchange('note_type')
    def _onchange_note_type(self):
        """Reset partner and invoices when note type changes"""
        self.invoice_ids = False
        self.partner_id = False

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
        """Reset partner and invoices when note type changes"""
        self.invoice_ids = False
        self.partner_id = False
        # Return domain for partner selection based on note type
        return {
            'domain': {
                'partner_id': [
                    ('id', 'in', self._get_valid_partners().ids)
                ]
            }
        }

    def _get_valid_partners(self):
        """Get partners that have valid unpaid invoices"""
        domain = [
            ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid'),
        ]
        
        if self.note_type == 'receivable':
            domain.append(('move_type', '=', 'out_invoice'))
        else:
            domain.append(('move_type', '=', 'in_invoice'))
            
        valid_invoices = self.env['account.move'].search(domain)
        return valid_invoices.mapped('partner_id')

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        """Reset invoices when partner changes and validate partner selection"""
        self.invoice_ids = False
        
        if self.partner_id:
            # Validate if partner has valid invoices
            valid_partners = self._get_valid_partners()
            if self.partner_id not in valid_partners:
                warning_msg = _('Selected partner has no valid unpaid invoices of type {}').format(
                    _('Customer Invoice') if self.note_type == 'receivable' else _('Vendor Bill')
                )
                return {
                    'warning': {
                        'title': _('Warning'),
                        'message': warning_msg,
                    }
                }
                
    @api.constrains('partner_id', 'invoice_ids')
    def _check_partner_invoices(self):
        """Validate partner and invoice relationship"""
        for record in self:
            if record.invoice_ids:
                invalid_invoices = record.invoice_ids.filtered(
                    lambda inv: inv.partner_id != record.partner_id
                )
                if invalid_invoices:
                    raise ValidationError(_(
                        'The following invoices do not belong to the selected partner:\n%s'
                    ) % '\n'.join(invalid_invoices.mapped('name')))

    @api.constrains('date', 'due_date')
    def _check_dates(self):
        for record in self:
            if record.due_date < record.date:
                raise ValidationError(_('Due date must be greater than or equal to the billing date.'))

    def action_add_invoices(self):
        """Open wizard to add invoices with enhanced validation"""
        self.ensure_one()
        if not self.partner_id:
            raise UserError(_('Please select a partner first.'))

        if not self.available_invoice_ids:
            raise UserError(_(
                'No valid unpaid invoices available for selection.\n'
                'All invoices are either already billed or fully paid.'
            ))

        if self.note_type == 'receivable':
            title = _('Select Customer Invoices')
            view_ref = 'account.view_out_invoice_tree'
        else:
            title = _('Select Vendor Bills')
            view_ref = 'account.view_in_invoice_tree'

        # Get view references
        tree_view = self.env.ref(view_ref)
        search_view = self.env.ref('account.view_account_invoice_filter')

        return {
            'name': title,
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list',
            'views': [(tree_view.id, 'list')],
            'search_view_id': search_view.id,
            'domain': [('id', 'in', self.available_invoice_ids.ids)],
            'target': 'new',
            'context': {
                'create': False,
                'edit': False,
                'delete': False,
                'default_partner_id': self.partner_id.id,
                'search_default_posted': 1,
                'no_breadcrumbs': True,
                'list_selection': True,
                'no_create': True,
                'no_open': True
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