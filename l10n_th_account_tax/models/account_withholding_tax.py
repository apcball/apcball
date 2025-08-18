# Copyright 2020 Ecosoft Co., Ltd (https://ecosoft.co.th/)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html)
from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

# Define constants locally to avoid circular import
INCOME_TAX_FORM = [
    ("1", "PIT1"),
    ("2", "PIT2"),
    ("3", "PIT3"),
    ("3a", "PIT3a"),
]

WHT_CERT_INCOME_TYPE = [
    ("1", "Salary / Wages"),
    ("2", "Interest"),
    ("3", "Dividends"),
    ("4", "Service Fees"),
    ("5", "Other"),
]


class AccountWithholdingTax(models.Model):
    _name = "account.withholding.tax"
    _description = "Account Withholding Tax"

    name = fields.Char(required=True)
    account_id = fields.Many2one(
        comodel_name="account.account",
        string="Withholding Tax Account",
        domain=[("wht_account", "=", True)],
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
        store=True,
    )
    wht_cert_income_type = fields.Selection(
        WHT_CERT_INCOME_TYPE,
        string="Type of Income",
        required=True,
        default="1",
    )
    wht_cert_income_desc = fields.Char(
        string="Income Description",
        default="Services",
    )
    income_tax_form = fields.Selection(
        INCOME_TAX_FORM,
        string="Income Tax Form",
        compute="_compute_income_tax_form",
        store=True,
    )

    @api.depends("pit_id", "amount")
    def _compute_income_tax_form(self):
        for rec in self:
            if rec.pit_id:
                rec.income_tax_form = rec.pit_id.income_tax_form
            else:
                rec.income_tax_form = False

    @api.constrains("is_pit")
    def _check_is_pit(self):
        pits = self.search_count([("is_pit", "=", True)])
        if pits > 1:
            raise ValidationError(
                _(
                    "You can only have 1 withholding tax type " + 
                    "as personal income tax."
                )
            )

    @api.depends("is_pit")
    def _compute_pit_id(self):
        PIT = self.env["personal.income.tax"]
        for rec in self:
            if rec.is_pit:
                # Find active PIT rate
                pit = PIT.search([("year", "<=", fields.Date.today().year)], 
                                order="year desc", limit=1)
                rec.pit_id = pit.id if pit else False
            else:
                rec.pit_id = False
