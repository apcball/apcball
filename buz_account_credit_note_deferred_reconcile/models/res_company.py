from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    buz_deferred_credit_note_reconcile = fields.Boolean(
        string="Deferred Credit Note Reconciliation",
        default=True,
        help="Prevent invoices and credit notes from being automatically "
             "reconciled when a reversal is created. Reconciliation must be "
             "performed manually by accounting users.",
    )
