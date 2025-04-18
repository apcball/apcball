from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

class BillingNote(models.Model):
    _name = 'billing.note'
    _description = 'Billing Note'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

    # Add indexes for better performance
    _sql_constraints = [
        ('name_uniq', 'unique(name, company_id)', 'Billing note number must be unique per company!'),
    ]

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
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
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

    def action_register_payment(self):
        """Open the standard payment wizard"""
        self.ensure_one()
        
        # Get invoices from billing note
        invoices = self.invoice_ids

        # Create context for the payment wizard
        ctx = {
            'active_model': 'account.move',
            'active_ids': invoices.ids,
        }

        # Return the action to open the payment wizard
        return {
            'name': _('Register Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': ctx,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    def action_register_batch_payment(self):
        """Open the batch payment wizard from account_payment_batch_process"""
        if not self:
            raise UserError(_('Please select at least one billing note.'))
            
        # Check if all selected billing notes have same type
        note_types = set(self.mapped('note_type'))
        if len(note_types) > 1:
            raise UserError(_('Selected billing notes must be of the same type (all receivable or all payable).'))
            
        # Check if all selected billing notes are in correct state
        invalid_states = self.filtered(lambda r: r.state != 'confirm' or r.payment_state == 'paid')
        if invalid_states:
            raise UserError(_('All selected billing notes must be confirmed and not fully paid.'))

        # Get all invoices from selected billing notes
        invoices = self.env['account.move']
        for note in self:
            invoices |= note.invoice_ids

        # Create context for the payment wizard
        ctx = {
            'active_model': 'account.move',
            'active_ids': invoices.ids,
        }

        # Return the action to open the batch payment wizard
        return {
            'name': _('Register Batch Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'view_id': self.env.ref('account_payment_batch_process.view_account_payment_register_form').id,
            'context': ctx,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

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
        # Return domain for partner selection based on note type
        return {
            'domain': {
                'partner_id': [('id', 'in', self._get_valid_partners().ids)]
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
            partner_domain = [('customer_rank', '>', 0)]
        else:
            domain.append(('move_type', '=', 'in_invoice'))
            partner_domain = [('supplier_rank', '>', 0)]

        invoices = self.env['account.move'].search(domain)
        partners = self.env['res.partner'].search(partner_domain)
        return partners.filtered(lambda p: p.id in invoices.mapped('partner_id').ids)

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
            old_state = rec.payment_state
            if rec.amount_paid <= 0:
                rec.payment_state = 'not_paid'
            elif rec.amount_paid >= rec.amount_total:
                rec.payment_state = 'paid'
            else:
                rec.payment_state = 'partial'
                
            # Send email notification when payment is received
            if old_state != rec.payment_state and rec.payment_state in ['partial', 'paid']:
                template = self.env.ref('buz_custom_billing_note.email_template_billing_note_payment')
                template.send_mail(rec.id, force_send=True)

    def action_confirm(self):
        """Confirm billing note"""
        for record in self:
            if not record.invoice_ids:
                raise UserError(_('Please add at least one invoice before confirming.'))
            if record.state != 'draft':
                continue
            record.write({
                'state': 'confirm',
                'name': self.env['ir.sequence'].next_by_code(
                    'customer.billing.note' if record.note_type == 'receivable' else 'vendor.billing.note'
                ) or '/'
            })

    def action_done(self):
        """Mark billing note as done"""
        for record in self:
            if record.state != 'confirm':
                continue
            record.write({'state': 'done'})

    def action_draft(self):
        """Reset billing note to draft"""
        for record in self:
            if record.state != 'confirm':
                continue
            record.write({'state': 'draft'})

    def action_cancel(self):
        """Cancel billing note"""
        for record in self:
            if record.state not in ['draft', 'confirm']:
                continue
            record.write({'state': 'cancel'})