from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)

class BillingNotePayment(models.Model):
    _name = 'billing.note.payment'
    _description = 'Billing Note Payment'
    _order = 'date desc, id desc'

    name = fields.Char(string='Reference', readonly=True, copy=False)
    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True, ondelete='cascade')
    payment_id = fields.Many2one('account.payment', string='Payment', readonly=True)
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    date = fields.Date(string='Date', required=True, default=fields.Date.context_today)
    amount = fields.Monetary(string='Amount', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', 
        related='billing_note_id.currency_id', store=True, readonly=True)
    company_id = fields.Many2one('res.company', string='Company',
        related='billing_note_id.company_id', store=True, readonly=True)
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('check', 'Check'),
        ('other', 'Other')
    ], string='Payment Method', required=True)
    notes = fields.Text(string='Notes')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                vals['name'] = self.env['ir.sequence'].next_by_code('billing.note.payment')
        return super().create(vals_list)

    @api.model
    def _create_from_payment(self, payment, billing_note, amount):
        """Create payment record from account.payment"""
        return self.create({
            'billing_note_id': billing_note.id,
            'payment_id': payment.id,
            'payment_date': payment.date,
            'date': payment.date,
            'amount': amount,
            'payment_method': self._get_payment_method(payment),
            'notes': f'Created from payment {payment.name}'
        })

    def _get_payment_method(self, payment):
        """Map account.payment method to billing note payment method"""
        # Map payment method based on journal type and payment method code
        if payment.journal_id.type == 'cash':
            return 'cash'
        elif payment.journal_id.type == 'bank':
            return 'bank'
        elif payment.payment_method_line_id.code == 'check_printing':
            return 'check'
        return 'other'

class AccountPayment(models.Model):
    _inherit = 'account.payment'

    def _post(self, soft=True):
        """Override to handle billing note payments"""
        res = super()._post(soft=soft)
        self.env['billing.note']._handle_payment_creation(self)
        return res
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
        ('in_payment', 'In Payment'),
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
            'default_payment_type': 'inbound' if self[0].note_type == 'receivable' else 'outbound',
            'default_partner_type': 'customer' if self[0].note_type == 'receivable' else 'supplier',
            'default_billing_notes': self.ids,  # Pass billing note IDs to context
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

    @api.depends('invoice_ids', 'invoice_ids.amount_total', 'invoice_ids.amount_residual', 'invoice_ids.payment_state')
    def _compute_amount_total(self):
        for record in self:
            record.amount_total = sum(record.invoice_ids.filtered(lambda x: x.state == 'posted').mapped('amount_total'))

    @api.depends('invoice_ids', 'invoice_ids.amount_total', 'invoice_ids.amount_residual', 'invoice_ids.payment_state')
    def _compute_amount_paid(self):
        for record in self:
            posted_invoices = record.invoice_ids.filtered(lambda x: x.state == 'posted')
            total = sum(posted_invoices.mapped('amount_total'))
            residual = sum(posted_invoices.mapped('amount_residual'))
            record.amount_paid = total - residual
            record.amount_residual = residual

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.amount_residual', 'invoice_ids.state')
    def _compute_payment_state(self):
        for record in self:
            if not record.invoice_ids:
                record.payment_state = 'not_paid'
                continue

            # กรองเฉพาะใบแจ้งหนี้ที่ posted แล้ว
            posted_invoices = record.invoice_ids.filtered(lambda x: x.state == 'posted')
            if not posted_invoices:
                record.payment_state = 'not_paid'
                continue

            # รวบรวมข้อมูลจากใบแจ้งหนี้
            payment_states = posted_invoices.mapped('payment_state')
            total_residual = sum(posted_invoices.mapped('amount_residual'))
            total_amount = sum(posted_invoices.mapped('amount_total'))

            # Debug log
            _logger.info(f'Billing Note {record.name} - Payment States: {payment_states}')
            _logger.info(f'Total Residual: {total_residual}, Total Amount: {total_amount}')

            # ตรวจสอบสถานะการชำระเงิน
            if all(state == 'paid' for state in payment_states):
                record.payment_state = 'paid'
            elif all(state == 'in_payment' for state in payment_states):
                record.payment_state = 'in_payment'
            elif any(state in ['in_payment', 'partial'] for state in payment_states) or \
                 (total_residual > 0 and total_residual < total_amount):
                record.payment_state = 'partial'
            else:
                record.payment_state = 'not_paid'

            _logger.info(f'Final Payment State: {record.payment_state}')

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

    @api.depends('invoice_ids', 'invoice_ids.amount_residual')
    def _compute_amount_total(self):
        for rec in self:
            rec.amount_total = sum(rec.invoice_ids.mapped('amount_residual'))

    @api.depends('amount_total', 'payment_line_ids.amount')
    def _compute_amount_paid(self):
        for rec in self:
            rec.amount_paid = sum(rec.payment_line_ids.mapped('amount'))
            rec.amount_residual = rec.amount_total - rec.amount_paid

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.amount_residual')
    def _compute_payment_state(self):
        for rec in self:
            old_state = rec.payment_state
            
            # Check if all invoices are paid
            all_paid = all(inv.payment_state == 'paid' for inv in rec.invoice_ids)
            any_paid = any(inv.payment_state in ['partial', 'paid'] for inv in rec.invoice_ids)
            
            if all_paid:
                rec.payment_state = 'paid'
            elif any_paid:
                rec.payment_state = 'partial'
            else:
                rec.payment_state = 'not_paid'
                
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

    def _create_payment_from_wizard(self, payment_vals):
        """Create payment record from payment wizard"""
        self.ensure_one()
        payment = self.env['account.payment'].create(payment_vals)
        
        # Create billing note payment record
        self.env['billing.note.payment']._create_from_payment(
            payment=payment,
            billing_note=self,
            amount=payment.amount
        )
        return payment

    @api.model
    def _handle_payment_creation(self, payment):
        """Handle payment creation for billing notes"""
        # Find related billing notes through invoices
        billing_notes = self.env['billing.note'].search([
            ('invoice_ids', 'in', payment.reconciled_invoice_ids.ids),
            ('state', '=', 'confirm')
        ])
        
        for note in billing_notes:
            # Calculate amount for this billing note
            note_invoices = note.invoice_ids & payment.reconciled_invoice_ids
            total_amount = sum(note_invoices.mapped('amount_total'))
            paid_amount = sum(note_invoices.mapped(lambda i: i.amount_total - i.amount_residual))
            payment_ratio = paid_amount / total_amount if total_amount else 0
            note_amount = payment.amount * payment_ratio

            if note_amount > 0:
                # Create billing note payment record
                self.env['billing.note.payment']._create_from_payment(
                    payment=payment,
                    billing_note=note,
                    amount=note_amount
                )