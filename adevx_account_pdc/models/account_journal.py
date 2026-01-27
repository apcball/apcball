from odoo import models, api, _


class AccountJournal(models.Model):
    _inherit = "account.journal"

    # =========================== Built-in functions =========================== #
    @api.model
    def _get_reusable_payment_methods(self):
        res = super()._get_reusable_payment_methods()
        res.add("pdc")
        return res
