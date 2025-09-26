Goal

When running the Clear Advance flow, posting the clearing JE must never fail due to a missing Entry Sequence on the configured clearing journal (usually Miscellaneous Operations).
If the journal has no sequence_id, the system must create & assign a proper ir.sequence automatically before posting.

Requirements

UI-safe: If users fix via UI (set Entry Sequence on the journal), flow works.

Code-safe: If not set, the wizard auto-creates a sequence at runtime.

Company-correct: Created sequence company_id matches journal’s company.

Idempotent: Do nothing if sequence_id already set.

No-gap & date-ranged prefix recommended: ADVCL/%(year)s/%(month)s/.

Implementation Steps

Add a tiny utility to ensure a journal sequence exists.

Call it in the Clear Advance wizard right before creating/posting the JE.

(Optional) Add a post_init_hook to backfill existing configs on install/upgrade.

Code (copy-paste)

A) Utility

# models/utils_journal.py  (or merge into an existing model file)
from odoo import api, models

class AdvanceJournalUtils(models.AbstractModel):
    _name = 'hr.expense.advance.journal.utils'
    _description = 'Utilities for Advance Clearing Journal'

    @api.model
    def ensure_journal_sequence(self, journal):
        """Ensure journal has an Entry Sequence; create one if missing."""
        if journal.sequence_id:
            return journal.sequence_id

        seq = self.env['ir.sequence'].create({
            'name': f'{journal.name} Entry Sequence',
            'code': f'ADVCL.{journal.id}',   # unique per journal
            'prefix': 'ADVCL/%(year)s/%(month)s/',
            'padding': 5,
            'implementation': 'no_gap',
            'use_date_range': True,
            'company_id': journal.company_id.id,
        })
        journal.sequence_id = seq.id
        return seq


B) Wizard hook

# wizard/bill_clear_advance_wizard.py
from odoo import models, _
from odoo.exceptions import UserError

class BillClearAdvanceWizard(models.TransientModel):
    _name = 'bill.clear.advance.wizard'
    _description = 'Clear Vendor Bill with Employee Advance'

    def action_confirm(self):
        self.ensure_one()
        bill = self._get_bill()                       # your existing getter
        journal = self._get_clearing_journal(bill)    # your existing resolver

        # ✅ Guarantee sequence exists before creating the JE
        self.env['hr.expense.advance.journal.utils'].ensure_journal_sequence(journal)

        move = self._create_clearing_move(bill, journal)  # your existing creator
        # continue with post/reconcile/message...
        return {'type': 'ir.actions.act_window_close'}


C) (Optional) Post-install backfill

# hooks.py
from odoo import SUPERUSER_ID
from odoo.api import Environment

def post_init_hook(cr, registry):
    env = Environment(cr, SUPERUSER_ID, {})
    utils = env['hr.expense.advance.journal.utils']
    # if you store journal in a config model:
    for cfg in env['hr.expense.config'].search([]):
        if cfg.clearing_journal_id:
            utils.ensure_journal_sequence(cfg.clearing_journal_id)


D) Manifest

# __manifest__.py
'post_init_hook': 'post_init_hook',


E) XML (optional if you prefer data-driven)
Use only when you control the journal record in data; otherwise prefer Python above.

<odoo>
  <record id="seq_advance_clearing" model="ir.sequence">
    <field name="name">Advance Clearing Sequence</field>
    <field name="code">ADVCL.DEFAULT</field>
    <field name="prefix">ADVCL/%(year)s/%(month)s/</field>
    <field name="padding">5</field>
    <field name="implementation">no_gap</field>
    <field name="use_date_range">True</field>
  </record>
</odoo>

Acceptance Criteria

Approving & clearing creates/post JEs without “no sequence configured” error.

If the journal already has a sequence → no duplicate sequences created.

Sequence names follow ADVCL/YYYY/MM/00001 pattern (or your chosen prefix).

Works correctly per company; multi-company respects journal.company.

Admin UI Fallback (for operators)

Accounting → Configuration → Journals → Open the clearing journal → Advanced Settings → Entry Sequence: create:

Name: Advance Clearing Sequence

Prefix: ADVCL/%(year)s/%(month)s/

Padding: 5

Implementation: No gap

Use subsequences per date range: ✓

Company: (match)