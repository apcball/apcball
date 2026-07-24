from odoo import _, api, fields, models


class MogenSopScenario(models.Model):
    _name = "mogen.sop.scenario"
    _description = "S&OP Scenario"
    _order = "company_id, code"
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char(required=True, copy=False, default=lambda self: _("New"))
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    description = fields.Html()
    scenario_type = fields.Selection(
        [
            ("base", "Base"),
            ("optimistic", "Optimistic"),
            ("pessimistic", "Pessimistic"),
            ("custom", "Custom"),
        ],
        required=True,
        default="custom",
    )
    sales_factor = fields.Float(required=True, default=1.0, digits=(16, 4))
    lead_time_factor = fields.Float(required=True, default=1.0, digits=(16, 4))
    purchase_cost_factor = fields.Float(required=True, default=1.0, digits=(16, 4))
    production_capacity_factor = fields.Float(
        required=True,
        default=1.0,
        digits=(16, 4),
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "company_code_unique",
            "unique(company_id, code)",
            "The scenario code must be unique per company.",
        ),
        (
            "positive_factors",
            "check(sales_factor > 0 AND lead_time_factor > 0 "
            "AND purchase_cost_factor > 0 AND production_capacity_factor > 0)",
            "Scenario factors must be greater than zero.",
        ),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for values in vals_list:
            if values.get("code", _("New")) == _("New"):
                values["code"] = (
                    sequence.with_company(values.get("company_id")).next_by_code(
                        "mogen.sop.scenario"
                    )
                    or _("New")
                )
        return super().create(vals_list)
