from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_is_zero, float_compare

class BatchPaymentWizard(models.TransientModel):
    _name = 'billing.note.batch.payment.wizard'
    _description = 'Batch Payment Processing Wizard'

    # Basic Fields
    billing_note_ids = fields.Many2many('billing.note', string='Billing Notes',
        domain="[('state', '=', 'confirm'), ('payment_state', 'in', ['not_paid', 'partial'])]")
    payment_date = fields.Date(string='Payment Date', required=True, default=fields.Date.context_today)
    journal_id = fields.Many2one('account.journal', string='Payment Journal', required=True,
        domain=[('type', 'in', ['bank', 'cash'])])
    payment_method = fields.Selection([
        ('cash', 'Cash'),
        ('bank', 'Bank Transfer'),
        ('check', 'Check'),
    ], string='Payment Method', required=True)
    memo = fields.Char(string='Memo')
    
    # Company and Currency
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company)
    currency_id = fields.Many2one('res.currency', string='Payment Currency', required=True,
        default=lambda self: self.env.company.currency_id)
    
    # Payment Options
    group_payment = fields.Boolean(string='Group Payments by Partner', default=True,
        help='If enabled, generates a single payment per partner')
    payment_type = fields.Selection([
        ('inbound', 'Receive Money'),
        ('outbound', 'Send Money'),
    ], string='Payment Type', required=True, default='inbound')
    partner_type = fields.Selection([
        ('customer', 'Customer'),
        ('supplier', 'Vendor'),
    ], string='Partner Type', required=True, default='customer')
    
    # Amount Fields
    amount = fields.Monetary(string='Payment Amount', required=True)
    total_residual = fields.Monetary(string='Total Residual', compute='_compute_total_residual',
        currency_field='currency_id')
    payment_difference = fields.Monetary(string='Payment Difference',
        compute='_compute_payment_difference', currency_field='currency_id')
    payment_difference_handling = fields.Selection([
        ('open', 'Keep Open'),
        ('reconcile', 'Mark as Fully Paid'),
        ('distribute', 'Distribute Difference')
    ], string='Payment Difference Handling', default='distribute',
        help='* Keep Open: Leave remaining amount open\n'
             '* Mark as Fully Paid: Mark invoice as fully paid\n'
             '* Distribute Difference: Distribute the difference across invoices')
    
    # Computed Fields
    available_partner_bank_ids = fields.Many2many('res.partner.bank', compute='_compute_available_partner_bank_accounts')
    partner_bank_id = fields.Many2one('res.partner.bank', string='Recipient Bank Account')
    show_partner_bank = fields.Boolean(compute='_compute_show_partner_bank')
    
    # Payment Lines for detailed view
    payment_line_ids = fields.One2many('billing.note.batch.payment.line.wizard', 'wizard_id', string='Payment Lines')

    @api.depends('billing_note_ids')
    def _compute_total_residual(self):
        for wizard in self:
            total = sum(wizard.billing_note_ids.mapped('amount_residual'))
            wizard.total_residual = total

    @api.depends('amount', 'total_residual')
    def _compute_payment_difference(self):
        for wizard in self:
            wizard.payment_difference = wizard.total_residual - wizard.amount

    @api.depends('payment_method', 'journal_id')
    def _compute_show_partner_bank(self):
        for wizard in self:
            wizard.show_partner_bank = wizard.payment_method == 'bank'

    @api.depends('partner_type', 'billing_note_ids')
    def _compute_available_partner_bank_accounts(self):
        for wizard in self:
            partners = wizard.billing_note_ids.mapped('partner_id')
            wizard.available_partner_bank_ids = partners.mapped('bank_ids')

    @api.onchange('billing_note_ids')
    def _onchange_billing_note_ids(self):
        self.amount = self.total_residual
        self._create_payment_lines()

    @api.onchange('journal_id')
    def _onchange_journal(self):
        if self.journal_id:
            if self.journal_id.type == 'cash':
                self.payment_method = 'cash'
            elif self.journal_id.type == 'bank':
                self.payment_method = 'bank'

    def _create_payment_lines(self):
        self.payment_line_ids = [(5, 0, 0)]
        if not self.billing_note_ids:
            return

        lines = []
        for note in self.billing_note_ids:
            lines.append((0, 0, {
                'billing_note_id': note.id,
                'partner_id': note.partner_id.id,
                'amount_residual': note.amount_residual,
                'amount_to_pay': note.amount_residual,
                'currency_id': note.currency_id.id,
            }))
        self.payment_line_ids = lines

    def _get_payment_method_line(self, journal):
        """Get appropriate payment method line based on payment type"""
        payment_method_lines = journal.inbound_payment_method_line_ids if self.payment_type == 'inbound' \
            else journal.outbound_payment_method_line_ids
        payment_method_line = payment_method_lines.filtered(
            lambda x: x.payment_method_id.code == 'manual'
        )
        if not payment_method_line:
            raise ValidationError(_('No manual payment method available for this journal.'))
        return payment_method_line[0]

    def _prepare_payment_vals(self, group):
        """Prepare payment values for account.payment creation"""
        payment_method_line = self._get_payment_method_line(self.journal_id)
        return {
            'date': self.payment_date,
            'amount': group['amount'],
            'payment_type': self.payment_type,
            'partner_type': self.partner_type,
            'partner_id': group['partner_id'],
            'journal_id': self.journal_id.id,
            'payment_method_line_id': payment_method_line.id,
            'partner_bank_id': self.partner_bank_id.id if self.show_partner_bank else False,
            'ref': self.memo or _('Batch payment: %s') % ', '.join(group['note_names']),
            'currency_id': group['currency_id'],
        }

    def _group_billing_notes(self):
        """Group billing notes by partner and currency if group_payment is enabled"""
        groups = []
        if self.group_payment:
            # Group by partner and currency
            partner_currency_groups = {}
            for line in self.payment_line_ids:
                key = (line.partner_id.id, line.currency_id.id)
                if key not in partner_currency_groups:
                    partner_currency_groups[key] = {
                        'partner_id': line.partner_id.id,
                        'currency_id': line.currency_id.id,
                        'amount': 0.0,
                        'notes': self.env['billing.note'],
                        'note_names': [],
                    }
                group = partner_currency_groups[key]
                group['amount'] += line.amount_to_pay
                group['notes'] |= line.billing_note_id
                group['note_names'].append(line.billing_note_id.name)
            groups.extend(partner_currency_groups.values())
        else:
            # Create individual payments
            for line in self.payment_line_ids:
                groups.append({
                    'partner_id': line.partner_id.id,
                    'currency_id': line.currency_id.id,
                    'amount': line.amount_to_pay,
                    'notes': line.billing_note_id,
                    'note_names': [line.billing_note_id.name],
                })
        return groups

    def _create_billing_note_payments(self, payment, notes, allocated_amount):
        """Create billing note payment records"""
        for note in notes:
            line = self.payment_line_ids.filtered(lambda l: l.billing_note_id == note)
            amount = line.amount_to_pay if line else allocated_amount
            
            self.env['billing.note.payment'].create({
                'billing_note_id': note.id,
                'payment_id': payment.id,
                'payment_date': self.payment_date,
                'payment_method': self.payment_method,
                'amount': amount,
                'notes': self.memo,
                'currency_id': note.currency_id.id,
                'company_id': note.company_id.id,
            })
            
            if float_compare(note.amount_residual, amount, precision_rounding=note.currency_id.rounding) <= 0:
                note.action_done()

    def action_create_payments(self):
        """Create and post payments"""
        self.ensure_one()
        if not self.billing_note_ids:
            raise UserError(_('Please select at least one billing note.'))

        if not self.payment_line_ids.filtered(lambda l: l.amount_to_pay > 0):
            raise UserError(_('No payment amounts specified.'))

        if self.payment_difference_handling == 'distribute':
            self._distribute_payment_difference()

        payments = self.env['account.payment']
        for group in self._group_billing_notes():
            # Create payment
            payment_vals = self._prepare_payment_vals(group)
            payment = payments.create(payment_vals)
            payments |= payment

            # Create billing note payments
            self._create_billing_note_payments(payment, group['notes'], group['amount'])

        # Post all payments
        payments.action_post()

        return {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', payments.ids)],
        }

    def _distribute_payment_difference(self):
        """Distribute payment difference across payment lines"""
        if float_is_zero(self.payment_difference, precision_rounding=self.currency_id.rounding):
            return

        total_residual = sum(self.payment_line_ids.mapped('amount_residual'))
        for line in self.payment_line_ids:
            ratio = line.amount_residual / total_residual
            line.amount_to_pay = line.amount_residual - (self.payment_difference * ratio)

class BatchPaymentLineWizard(models.TransientModel):
    _name = 'billing.note.batch.payment.line.wizard'
    _description = 'Batch Payment Line Wizard'

    wizard_id = fields.Many2one('billing.note.batch.payment.wizard', string='Wizard')
    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True)
    partner_id = fields.Many2one('res.partner', string='Partner', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', required=True)
    amount_residual = fields.Monetary(string='Amount Due', currency_field='currency_id')
    amount_to_pay = fields.Monetary(string='Amount to Pay', currency_field='currency_id')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        if self._context.get('active_model') == 'billing.note' and self._context.get('active_ids'):
            billing_notes = self.env['billing.note'].browse(self._context['active_ids'])
            # Check if all billing notes have same currency
            currencies = billing_notes.mapped('currency_id')
            if len(currencies) > 1:
                raise UserError(_('Selected billing notes must have the same currency.'))
            res['billing_note_ids'] = [(6, 0, self._context['active_ids'])]
        return res

    def _prepare_payment_vals(self, partner, notes, allocated_amount):
        """Prepare values for account.payment creation"""
        # Find appropriate payment method line
        journal_type = 'bank' if self.payment_method in ['bank', 'check'] else 'cash'
        payment_type = 'inbound'  # Since we're handling customer payments
        payment_method_line = self.journal_id.inbound_payment_method_line_ids.filtered(
            lambda x: x.payment_method_id.code == 'manual'
        )
        
        if not payment_method_line:
            raise ValidationError(_('No manual payment method available for this journal.'))

        return {
            'payment_type': payment_type,
            'partner_type': 'customer',
            'partner_id': partner.id,
            'amount': allocated_amount,
            'date': self.payment_date,
            'journal_id': self.journal_id.id,
            'payment_method_line_id': payment_method_line[0].id,
            'ref': self.memo or _('Batch payment for billing notes: %s') % ', '.join(notes.mapped('name')),
            'currency_id': notes[0].currency_id.id,
        }

    def action_create_payments(self):
        self.ensure_one()
        if not self.billing_note_ids:
            raise UserError(_('Please select at least one billing note.'))

        # Group billing notes by partner and currency
        partner_notes = {}
        for note in self.billing_note_ids:
            key = (note.partner_id, note.currency_id)
            if key not in partner_notes:
                partner_notes[key] = []
            partner_notes[key].append(note)

        # Calculate allocation ratio
        total_residual = sum(self.billing_note_ids.mapped('amount_residual'))
        allocation_ratio = self.amount / total_residual if total_residual else 0

        # Create payments for each partner
        payments = self.env['account.payment']
        for (partner, currency), notes in partner_notes.items():
            partner_total = sum(note.amount_residual for note in notes)
            allocated_amount = partner_total * allocation_ratio

            # Create payment
            payment_vals = self._prepare_payment_vals(partner, notes, allocated_amount)
            payment = payments.create(payment_vals)
            payments |= payment

            # Create billing note payments and update states
            for note in notes:
                note_allocation = note.amount_residual * allocation_ratio
                self.env['billing.note.payment'].create({
                    'billing_note_id': note.id,
                    'payment_id': payment.id,
                    'payment_date': self.payment_date,
                    'payment_method': self.payment_method,
                    'amount': note_allocation,
                    'notes': self.memo,
                    'currency_id': note.currency_id.id,
                    'company_id': note.company_id.id,
                })
                
                # Update billing note state if fully paid
                if note.amount_residual <= note_allocation:
                    note.action_done()

        # Post all payments
        payments.action_post()

        return {
            'name': _('Payments'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.payment',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', payments.ids)],
        }