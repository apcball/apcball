from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    buz_deferred_credit_note_reconcile = fields.Boolean(
        related="company_id.buz_deferred_credit_note_reconcile",
        readonly=False,
        string="Deferred Credit Note Reconciliation",
    )
