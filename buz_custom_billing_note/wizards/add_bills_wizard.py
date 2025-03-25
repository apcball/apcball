from odoo import models, fields, api

class AddBillsWizard(models.TransientModel):
    _name = 'add.bills.wizard'
    _description = 'Add Documents Wizard'

    billing_note_id = fields.Many2one('billing.note', string='Billing Note', required=True)
    note_type = fields.Selection(related='billing_note_id.note_type', readonly=True)
    partner_id = fields.Many2one(related='billing_note_id.partner_id', readonly=True)

    invoice_ids = fields.Many2many(
        'account.move',
        string='Documents to Add'
    )

    @api.onchange('billing_note_id')
    def _onchange_billing_note(self):
        domain = [
            ('partner_id', '=', self.partner_id.id),
            ('state', '=', 'posted'),
            ('payment_state', '!=', 'paid')
        ]

        if self.note_type == 'receivable':
            domain.append(('move_type', '=', 'out_invoice'))
        else:
            domain.append(('move_type', '=', 'in_invoice'))

        return {'domain': {'invoice_ids': domain}}

    def action_add_invoices(self):
        self.ensure_one()
        if self.invoice_ids:
            self.billing_note_id.write({
                'invoice_ids': [(4, inv_id) for inv_id in self.invoice_ids.ids]
            })
        return {'type': 'ir.actions.act_window_close'}