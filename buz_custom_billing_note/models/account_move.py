from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_number = fields.Char(string='Tax Invoice Number', default='')
    vendor_bill_number = fields.Char(string='Vendor Bill Number')

    billing_note_ids = fields.Many2many(
        'billing.note',
        'billing_note_invoice_rel',  # Using the same relation table as in billing.note model
        'invoice_id',
        'billing_note_id',
        string='Billing Notes'
    )

    def action_create_billing_note(self):
        """Create a new billing note from this invoice."""
        self.ensure_one()

        if self.state != 'posted':
            raise UserError(_('You can only create billing notes for posted invoices.'))

        if not self.partner_id:
            raise UserError(_('Invoice must have a partner.'))

        if not self.invoice_date_due:
            raise UserError(_('Invoice must have a due date.'))

        if self.move_type not in ['out_invoice', 'in_invoice']:
            raise UserError(_('You can only create billing notes for customer invoices or vendor bills.'))

        # Check if invoice is already in a non-cancelled billing note
        existing_note = self.env['billing.note'].search([
            ('invoice_ids', 'in', self.id),
            ('state', '!=', 'cancel')
        ], limit=1)
        
        if existing_note:
            raise UserError(_('This invoice is already included in billing note %s') % existing_note.name)

        # Determine the note type based on the invoice type
        note_type = 'payable' if self.move_type == 'in_invoice' else 'receivable'

        vals = {
            'partner_id': self.partner_id.id,
            'date': fields.Date.context_today(self),
            'due_date': self.invoice_date_due,
            'company_id': self.company_id.id,
            'currency_id': self.currency_id.id,
            'note_type': note_type,
            'invoice_ids': [(4, self.id)],
        }

        # Create the billing note
        billing_note = self.env['billing.note'].create(vals)

        return {
            'name': _('Billing Note'),
            'type': 'ir.actions.act_window',
            'res_model': 'billing.note',
            'res_id': billing_note.id,
            'view_mode': 'form',
            'target': 'current',
        }