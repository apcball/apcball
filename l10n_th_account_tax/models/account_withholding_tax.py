# Copyright 2020 Ecosoft Co., Ltd (https://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .withholding_tax_cert import INCOME_TAX_FORM, WHT_CERT_INCOME_TYPE


class AccountWithholdingTax(models.Model):
    _name = "account.withholding.tax"
    _description = "Account Withholding Tax"
    _check_company_auto = True

    name = fields.Char(required=True)
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Withholding Tax Account",
    # No domain restriction so any chart of account can be selected from the dropdown
        required=True,
        ondelete="restrict",
    )
    amount = fields.Float(
        string="Percent",
    )
    is_pit = fields.Boolean(
        string="Personal Income Tax",
        help="As PIT, the calculation of withholding amount is based on pit.rate",
    )
    pit_id = fields.Many2one(
        comodel_name="personal.income.tax",
        string="PIT Rate",
        compute="_compute_pit_id",
        help="Latest PIT Rates used to calcuate withholiding amount",
    )
    income_tax_form = fields.Selection(
        selection=INCOME_TAX_FORM,
        string="Default Income Tax Form",
    )
    wht_cert_income_type = fields.Selection(
        selection=WHT_CERT_INCOME_TYPE,
        string="Default Type of Income",
    )
    company_id = fields.Many2one(
        comodel_name="res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    # ...existing code...

    _sql_constraints = [
        ("name_unique", "UNIQUE(name,company_id)", "Name must be unique!"),
    ]

    @api.constrains("is_pit")
    def _check_is_pit(self):
        pits = self.search_count([("is_pit", "=", True)])
        if pits > 1:
            raise ValidationError(self.env._("Only 1 personal income tax allowed!"))

    # Removed constraint that required selected account to have wht_account=True
    # so users can choose existing chart of accounts freely. If you want to
    # enforce WHT accounts only, re-add this constraint or set the
    # 'wht_account' flag on the desired accounts.

    @api.depends("is_pit")
    def _compute_pit_id(self):
        pit_date = self.env.context.get("pit_date") or fields.Date.context_today(self)
        pit = self.env["personal.income.tax"].search(
            [("effective_date", "<=", pit_date)], order="effective_date desc", limit=1
        )
        self.update({"pit_id": pit.id})
