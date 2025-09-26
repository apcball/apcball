from odoo import api, fields, models, _
from odoo.exceptions import UserError


class AdvanceRefillBaseWizard(models.TransientModel):
    _name = 'advance.refill.base.wizard'
    _description = 'Advance Refill to Base Wizard'

    advance_box_id = fields.Many2one(
        'employee.advance.box',
        string='Advance Box',
        required=True
    )
    current_balance = fields.Monetary(
        string='Current Balance',
        currency_field='currency_id'
    )
    base_amount_ref = fields.Monetary(
        string='Base Amount',
        currency_field='currency_id'
    )
    topup_amount = fields.Monetary(
        string='Top-up Amount',
        currency_field='currency_id'
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id
    )

    def action_confirm(self):
        """Confirm refill and create journal entry"""
        self.ensure_one()
        advance_box = self.advance_box_id

        # Check if required fields are set
        if not advance_box.account_id:
            raise UserError(_("Please set the advance account for the selected advance box."))
        if not advance_box.journal_id:
            raise UserError(_("Please set the journal for advance transactions."))
        partner = advance_box._get_employee_partner()
        if not partner:
            raise UserError(_("Please set the employee's private address."))

        if self.topup_amount <= 0:
            raise UserError(_("Top-up amount must be greater than zero."))

        # Create journal entry
        # Ensure journal has sequence
        if not getattr(advance_box.journal_id, 'sequence_id', False):
            raise UserError(_('The selected journal for advance refill does not have a sequence configured. Please set a sequence on the journal.'))

        je_vals = {
            'journal_id': advance_box.journal_id.id,
            'company_id': advance_box.company_id.id or self.env.company.id,
            'move_type': 'entry',
            'date': fields.Date.context_today(self),
            'ref': f'Refill Advance to Base for {advance_box.employee_id.name}',
            'line_ids': [
                (0, 0, {
                    'account_id': advance_box.account_id.id,
                    'partner_id': partner,
                    'debit': self.topup_amount,
                    'credit': 0.0,
                    'name': f'Refill Advance to Base for {advance_box.employee_id.name}'
                }),
                (0, 0, {
                    'account_id': advance_box.journal_id.default_account_id.id,
                    'debit': 0.0,
                    'credit': self.topup_amount,
                    'name': f'Refill Advance to Base for {advance_box.employee_id.name}'
                }),
            ]
        }

        # Create without explicit 'name' so the posting will assign sequence-based name
        je = self.env['account.move'].create(je_vals)
        je.action_post()

        # Update remember_base_amount in advance box
        advance_box.remember_base_amount = self.base_amount_ref

        # Force refresh of the balance by triggering recomputation
        advance_box._trigger_balance_recompute()

        # Log in chatter
        advance_box.message_post(
            body=_("Advance box refilled to base amount of %s. Journal entry: %s" % 
                  (self.base_amount_ref, je.name))
        )

        return je