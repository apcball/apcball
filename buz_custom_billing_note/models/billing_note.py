from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare
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

class BillingNote(models.Model):
    _name = 'billing.note'
    _description = 'Billing Note'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc, id desc'

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
    
    amount_paid = fields.Monetary(string='Amount Paid', compute='_compute_amount_paid', store=True)
    amount_residual = fields.Monetary(string='Amount Due', compute='_compute_amount_paid', store=True)
    payment_state = fields.Selection([
        ('not_paid', 'Not Paid'),
        ('in_payment', 'In Payment'),
        ('partial', 'Partially Paid'),
        ('paid', 'Paid'),
        ('reversed', 'Reversed'),
        ('invoicing_legacy', 'Invoicing App Legacy')
    ], string='Payment Status', compute='_compute_payment_state', store=True)
    payment_line_ids = fields.One2many('billing.note.payment', 'billing_note_id', string='Payments')
    
    notification_sent = fields.Boolean(string='Notification Sent', default=False)
    days_before_due = fields.Integer(string='Days Before Due for Notification', default=7)

    messenger_sent_date = fields.Date(string='วันที่ส่งแมสเซนเจอร์', tracking=True)
    messenger_received_date = fields.Date(string='วันที่รับจากแมสเซนเจอร์', tracking=True)
    ar_sent_date = fields.Date(string='วันที่ส่งบัญชีลูกหนี้', tracking=True)
    ar_received_date = fields.Date(string='วันที่บัญชีลูกหนี้รับ', tracking=True)
    expected_payment_date = fields.Date(string='วันที่คาดว่าจะได้รับเงิน', tracking=True)
    note = fields.Text(string='หมายเหตุ', tracking=True)

    @api.depends('partner_id', 'note_type')
    def _compute_available_invoices(self):
        """Compute available invoices for selection"""
        for rec in self:
            # Clear the field if no partner is selected
            if not rec.partner_id:
                rec.available_invoice_ids = self.env['account.move']
                continue

            domain = [
                ('partner_id', '=', rec.partner_id.id),
                ('state', '=', 'posted'),
                ('payment_state', 'not in', ['paid', 'in_payment']),  # Exclude fully paid and in-payment invoices
                ('amount_residual', '>', 0),  # Must have remaining amount to pay
            ]
            
            # Only exclude invoices from other billing notes if this is an existing record
            if not rec._origin.id:
                used_invoices = self.env['account.move']
            else:
                used_invoices = self.env['billing.note'].search([
                    ('id', '!=', rec._origin.id),  # Exclude current billing note
                    ('state', 'in', ['confirm', 'done']),  # Only consider confirmed/done billing notes
                ]).mapped('invoice_ids')
                if used_invoices:
                    domain.append(('id', 'not in', used_invoices.ids))  # Exclude invoices already in other billing notes
            
            if rec.note_type == 'receivable':
                domain.extend([
                    ('move_type', '=', 'out_invoice'),
                ])
            else:
                domain.extend([
                    ('move_type', '=', 'in_invoice'),
                ])
            
            rec.available_invoice_ids = self.env['account.move'].search(domain)

    @api.depends('invoice_ids', 'invoice_ids.amount_total')
    def _compute_amount_total(self):
        """Compute total amount from invoices"""
        for rec in self:
            # Use amount_total to show actual total amount of invoices
            rec.amount_total = sum(rec.invoice_ids.mapped('amount_total'))

    @api.depends('invoice_ids', 'invoice_ids.payment_state', 'invoice_ids.amount_residual', 'payment_line_ids', 'payment_line_ids.amount')
    def _compute_payment_state(self):
        precision = self.env['decimal.precision'].precision_get('Payment Terms')
        for rec in self:
            if not rec.invoice_ids:
                rec.payment_state = 'not_paid'  # ถ้าไม่มีใบแจ้งหนี้ถือว่ายังไม่ได้จ่าย
            elif float_is_zero(rec.amount_total, precision_digits=precision):
                rec.payment_state = 'paid'  # ถ้ายอดรวมเป็น 0
            else:
                # Calculate total residual amount from invoices
                total_residual = sum(rec.invoice_ids.mapped('amount_residual'))
                
                if float_is_zero(total_residual, precision_digits=precision):
                    rec.payment_state = 'paid'  # จ่ายครบแล้ว
                elif float_compare(total_residual, rec.amount_total, precision_digits=precision) == 0:
                    rec.payment_state = 'not_paid'  # ยังไม่มีการจ่ายเลย
                elif any(inv.payment_state == 'in_payment' for inv in rec.invoice_ids):
                    rec.payment_state = 'in_payment'  # มีการจ่ายเงินอยู่ในระหว่างดำเนินการ
                else:
                    rec.payment_state = 'partial'  # จ่ายบางส่วน

    @api.depends('invoice_ids', 'invoice_ids.amount_total', 'invoice_ids.amount_residual')
    def _compute_amount_paid(self):
        """Compute amount paid and amount residual"""
        for rec in self:
            # Calculate total residual from invoices
            total_residual = sum(rec.invoice_ids.mapped('amount_residual'))
            # Amount paid is the difference between total and residual
            rec.amount_paid = rec.amount_total - total_residual
            rec.amount_residual = total_residual

    def _handle_payment_creation(self, payments):
        """Handle payment creation from account.payment"""
        for payment in payments:
            # Find related billing notes through invoices
            billing_notes = self.env['billing.note'].search([
                ('invoice_ids', 'in', payment.reconciled_invoice_ids.ids),
                ('state', '=', 'confirm'),
            ])
            
            for note in billing_notes:
                # Get invoices that are both in the billing note and reconciled by this payment
                note_invoices = note.invoice_ids & payment.reconciled_invoice_ids
                
                # Calculate the actual payment amount for these invoices
                payment_amount = 0
                for inv in note_invoices:
                    # Get the payment amount for this specific invoice
                    reconciled_amount = sum(
                        line.amount
                        for line in payment.move_id.line_ids
                        if line.account_type in ('asset_receivable', 'liability_payable')
                        and line.partner_id == inv.partner_id
                    )
                    payment_amount += reconciled_amount
                
                if payment_amount > 0:
                    # Create payment record
                    self.env['billing.note.payment']._create_from_payment(payment, note, payment_amount)
                
                # Create payment record
                self.env['billing.note.payment']._create_from_payment(payment, note, payment_amount)

    @api.model
    def create(self, vals):
        if vals.get('name', '/') == '/':
            # Get the correct sequence code based on note type
            if vals.get('note_type') == 'receivable':
                sequence_code = 'customer.billing.note'
            else:
                sequence_code = 'vendor.billing.note'
            vals['name'] = self.env['ir.sequence'].next_by_code(sequence_code) or '/'
        return super(BillingNote, self).create(vals)

    @api.onchange('invoice_ids')
    def _onchange_invoice_ids(self):
        """Auto fill due date from first selected invoice"""
        if self.invoice_ids:
            # Sort invoices by due date to get the earliest one
            sorted_invoices = self.invoice_ids.sorted(lambda x: x.invoice_date_due or fields.Date.context_today(self))
            first_invoice = sorted_invoices[0]
            if first_invoice.invoice_date_due:
                self.due_date = first_invoice.invoice_date_due

    def action_confirm(self):
        """Confirm billing note"""
        for rec in self:
            if not rec.invoice_ids:
                raise UserError(_('Please select at least one document.'))
            rec.write({'state': 'confirm'})

    def action_done(self):
        """Mark billing note as done"""
        for rec in self:
            rec.write({'state': 'done'})

    def action_draft(self):
        """Reset billing note to draft"""
        for rec in self:
            rec.write({'state': 'draft'})

    def action_cancel(self):
        """Cancel billing note"""
        for rec in self:
            rec.write({'state': 'cancel'})

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
        """Open the batch payment wizard"""
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
            'default_billing_notes': self.ids,
        }

        # Return the action to open the batch payment wizard
        return {
            'name': _('Register Batch Payment'),
            'res_model': 'account.payment.register',
            'view_mode': 'form',
            'context': ctx,
            'target': 'new',
            'type': 'ir.actions.act_window',
        }