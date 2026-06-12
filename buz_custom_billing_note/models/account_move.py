from odoo import models, fields, api, _
from odoo.exceptions import UserError

class AccountMove(models.Model):
    _inherit = 'account.move'

    tax_invoice_number = fields.Char(string='Tax Invoice Number', default='')
    vendor_bill_number = fields.Char(string='Vendor Bill Number')
    payment_id = fields.Many2one('account.payment', string="Payment Ref")
    payment_type = fields.Selection(related='payment_id.payment_type', store=True)
    payment_method_id = fields.Many2one(related='payment_id.payment_method_id', store=True)
    check_number = fields.Char(related='payment_id.check_number', store=True)
    partner_bank_id = fields.Many2one(related='payment_id.partner_bank_id', store=True)
    billing_note_ids = fields.Many2many(
        'billing.note',
        'billing_note_invoice_rel',  # Using the same relation table as in billing.note model
        'invoice_id',
        'billing_note_id',
        string='Billing Notes'
    )

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