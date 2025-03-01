from odoo import models, fields, api
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_number = fields.Char(string='Tax Invoice Number', default='')
    vendor_bill_number = fields.Char(string='Vendor Bill Number')

    billing_note_ids = fields.Many2many(
        'billing.note',
        'billing_note_account_move_rel',
        'move_id',
        'billing_note_id',
        string='Billing Notes'
    )

    def action_create_billing_note(self):
        self.ensure_one()

        if self.state != 'posted':
            raise UserError('You can only create billing notes for posted invoices.')

        if not self.partner_id:
            raise UserError('Invoice must have a partner.')

        if not self.invoice_date_due:
            raise UserError('Invoice must have a due date.')

        # Determine the note type based on the bill type
        note_type = 'payable' if self.move_type == 'in_invoice' else 'receivable'

        # Determine the sequence code based on the note type
        sequence_code = 'vendor.billing.note' if note_type == 'payable' else 'customer.billing.note'

        vals = {
            'partner_id': self.partner_id.id,
            'date': fields.Date.context_today(self),
            'due_date': self.invoice_date_due,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'invoice_ids': [(4, self.id)],
            'line_ids': [(0, 0, {
                'name': self.name or '',
                'amount': self.amount_total
            })],
            'note_type': note_type  # Set the note type
        }

        # Create the billing note
        billing_note = self.env['billing.note'].create(vals)

        # Set the name field using the sequence
        if billing_note.name == '/':
            billing_note.name = self.env['ir.sequence'].next_by_code(sequence_code)

        return {
            'name': 'Billing Note',
            'type': 'ir.actions.act_window',
            'res_model': 'billing.note',
            'res_id': billing_note.id,
            'view_mode': 'form',
            'target': 'current',
        }