from odoo import api, models

class AdvanceJournalUtils(models.AbstractModel):
    _name = 'hr.expense.advance.journal.utils'
    _description = 'Utilities for Advance Clearing Journal'

    @api.model
    def ensure_journal_sequence(self, journal):
        """Ensure journal has an Entry Sequence; create one if missing."""
        # In Odoo 17, the account journal model should have sequence_id
        # But to avoid the attribute error, let's check if this field is available
        journal_fields = journal.fields_get()
        if 'sequence_id' in journal_fields:
            if journal.exists() and journal.sequence_id:
                return journal.sequence_id

        # Create a new sequence if not found
        new_seq = self.env['ir.sequence'].create({
            'name': f'{journal.name} Entry Sequence',
            'code': f'ADVCL.{journal.id}',   # unique per journal
            'prefix': 'ADVCL/%(year)s/%(month)s/',
            'padding': 5,
            'implementation': 'no_gap',
            'use_date_range': True,
            'company_id': journal.company_id.id,
        })

        # Only try to update the field if it exists
        if 'sequence_id' in journal_fields:
            journal.write({'sequence_id': new_seq.id})

        return new_seq