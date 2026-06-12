from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CreateBillingNoteWizard(models.TransientModel):
    _name = 'create.billing.note.wizard'
    _description = 'Create Billing Note Wizard'

    invoice_id = fields.Many2one(
        'account.move', string='Invoice', readonly=True)
    date = fields.Date(
        string='Document Date', required=True,
        default=fields.Date.context_today)
    note_type = fields.Selection([
        ('receivable', 'Customer Invoice'),
        ('payable', 'Vendor Bill'),
    ], string='Type', readonly=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            invoice = self.env['account.move'].browse(active_id)
            res['invoice_id'] = invoice.id
            res['note_type'] = 'payable' if invoice.move_type == 'in_invoice' else 'receivable'
        return res

    def action_create_billing_note(self):
        self.ensure_one()
        invoice = self.invoice_id

        if invoice.state != 'posted':
            raise UserError(_('You can only create billing notes for posted invoices.'))
        if not invoice.partner_id:
            raise UserError(_('Invoice must have a partner.'))
        if not invoice.invoice_date_due:
            raise UserError(_('Invoice must have a due date.'))

        # Check if invoice is already in a non-cancelled billing note
        existing_note = self.env['billing.note'].search([
            ('invoice_ids', 'in', invoice.id),
            ('state', '!=', 'cancel'),
        ], limit=1)
        if existing_note:
            raise UserError(
                _('This invoice is already included in billing note %s') % existing_note.name)

        note_type = 'payable' if invoice.move_type == 'in_invoice' else 'receivable'

        billing_note = self.env['billing.note'].create({
            'partner_id': invoice.partner_id.id,
            'date': self.date,
            'due_date': invoice.invoice_date_due,
            'company_id': invoice.company_id.id,
            'currency_id': invoice.currency_id.id,
            'note_type': note_type,
            'invoice_ids': [(4, invoice.id)],
        })

        return {
            'name': _('Billing Note'),
            'type': 'ir.actions.act_window',
            'res_model': 'billing.note',
            'res_id': billing_note.id,
            'view_mode': 'form',
            'target': 'current',
        }
