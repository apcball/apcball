# Copyright 2021 Ecosoft Co., Ltd. (http://ecosoft.co.th)
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models

from .withholding_tax_cert import INCOME_TAX_FORM, WHT_CERT_INCOME_TYPE


class WithholdingTaxCodeIncome(models.Model):
    _name = "withholding.tax.code.income"
    _description = "Withholding Tax Code Income"

    name = fields.Char(string="Name", required=True)
    code = fields.Char(string="Code", required=True)
    description = fields.Text(string="Description")
    active = fields.Boolean(string="Active", default=True)
    income_tax_form = fields.Selection(
        selection=INCOME_TAX_FORM,
        string="Income Tax Form",
        required=True,
    )
    wht_cert_income_type = fields.Selection(
        selection=WHT_CERT_INCOME_TYPE,
        string="Type of Income",
        required=True,
    )

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "Code must be unique!"),
    ]