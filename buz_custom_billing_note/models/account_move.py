from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_number = fields.Char(string='Tax Invoice Number', default='')
    vendor_bill_number = fields.Char(string='Vendor Bill Number')
    payment_id = fields.Many2one('account.payment', string="Payment Ref")
    payment_type = fields.Selection(
        string='Payment Type',
        compute='_compute_payment_fields', store=True,
        selection=[('outbound', 'Send Money'), ('inbound', 'Receive Money')],
    )
    payment_method_id = fields.Many2one(
        'account.payment.method', string='Payment Method',
        compute='_compute_payment_fields', store=True,
    )
    check_number = fields.Char(
        string='Check Number',
        compute='_compute_payment_fields', store=True,
    )
    partner_bank_id = fields.Many2one(
        'res.partner.bank', string='Partner Bank',
        compute='_compute_payment_fields', store=True,
    )

    @api.depends('payment_id')
    def _compute_payment_fields(self):
        for move in self:
            payment = move.payment_id
            move.payment_type = payment.payment_type if payment else False
            move.payment_method_id = payment.payment_method_id if payment else False
            move.check_number = payment.check_number if payment else False
            move.partner_bank_id = payment.partner_bank_id if payment else False
    billing_note_ids = fields.Many2many(
        'billing.note',
        'billing_note_invoice_rel',  # Using the same relation table as in billing.note model
        'invoice_id',
        'billing_note_id',
        string='Billing Notes'
    )
    billing_note_name = fields.Char(
        string='Billing Note',
        compute='_compute_billing_note_data',
        store=True,
    )
    billing_note_state = fields.Selection(
        string='Billing Note Status',
        compute='_compute_billing_note_data',
        store=True,
        selection=[
            ('draft', 'Draft'),
            ('confirm', 'Confirmed'),
            ('done', 'Done'),
            ('cancel', 'Cancelled'),
        ],
    )
    billing_note_payment_state = fields.Selection(
        string='Billing Note Payment',
        compute='_compute_billing_note_data',
        store=True,
        selection=[
            ('not_paid', 'Not Paid'),
            ('in_payment', 'In Payment'),
            ('partial', 'Partially Paid'),
            ('paid', 'Paid'),
            ('reversed', 'Reversed'),
            ('invoicing_legacy', 'Invoicing App Legacy'),
        ],
    )

    @api.depends('billing_note_ids', 'billing_note_ids.name', 'billing_note_ids.state', 'billing_note_ids.payment_state')
    def _compute_billing_note_data(self):
        for move in self:
            first_note = move.billing_note_ids[:1]
            move.billing_note_name = first_note.name if first_note else False
            move.billing_note_state = first_note.state if first_note else False
            move.billing_note_payment_state = first_note.payment_state if first_note else False

    def action_create_billing_note(self):
        """Open wizard to create a billing note from this invoice."""
        self.ensure_one()
        if self.state != 'posted':
            raise UserError(_('You can only create billing notes for posted invoices.'))
        if self.move_type not in ('out_invoice', 'in_invoice'):
            raise UserError(_('You can only create billing notes for customer invoices or vendor bills.'))

        return {
            'name': _('Create Billing Note'),
            'type': 'ir.actions.act_window',
            'res_model': 'create.billing.note.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_invoice_id': self.id,
                'default_note_type': 'payable' if self.move_type == 'in_invoice' else 'receivable',
            },
        }