# © 2017 Akretion (Alexis de Lattre <alexis.delattre@akretion.com>)
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).


from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class Agreement(models.Model):
    _name = "agreement"
    _description = "Agreement"
    _inherit = ["mail.thread", "mail.activity.mixin"]

    code = fields.Char(required=True, tracking=True)
    name = fields.Char(required=True, tracking=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Partner",
        ondelete="restrict",
        tracking=True,
    )
    partner_code = fields.Char(
        string="Partner Code",
        index=True,
        tracking=True,
        help="The partner's internal reference. Only codes starting with C "
        "can be used on an agreement.",
    )
    commercial_partner_id = fields.Many2one(
        "res.partner",
        string="Commercial Entity",
        compute="_compute_commercial_partner_id",
        tracking=True,
        precompute=True,
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        string="Company",
        default=lambda self: self.env.company,
    )
    is_template = fields.Boolean(
        string="Is a Template?",
        copy=False,
        help="Set if the agreement is a template. "
        "Template agreements don't require a partner.",
    )
    agreement_type_id = fields.Many2one(
        "agreement.type",
        string="Agreement Type",
        help="Select the type of agreement",
    )
    domain = fields.Selection(
        selection="_domain_selection",
        compute="_compute_domain",
        tracking=True,
        store=True,
        readonly=False,
    )
    active = fields.Boolean(default=True)
    signature_date = fields.Date(tracking=True)
    start_date = fields.Date(tracking=True)
    end_date = fields.Date(tracking=True)

    @api.model
    def _domain_selection(self):
        return [
            ("sale", _("Sale")),
            ("purchase", _("Purchase")),
        ]

    @api.depends("partner_id")
    def _compute_commercial_partner_id(self):
        for rec in self:
            rec.commercial_partner_id = rec.partner_id.commercial_partner_id

    @api.onchange("partner_id")
    def _onchange_partner_id_partner_code(self):
        """Keep the manually editable code aligned with the selected partner."""
        if self.partner_id:
            self.partner_code = self.partner_id.ref or False
        else:
            self.partner_code = False

    @api.onchange("partner_code")
    def _onchange_partner_code_partner_id(self):
        """Allow users to find the partner by entering its exact code."""
        code = (self.partner_code or "").strip()
        self.partner_code = code or False
        if not code:
            self.partner_id = False
            return
        if not code.startswith("C"):
            self.partner_id = False
            return {
                "warning": {
                    "title": _("Invalid Partner Code"),
                    "message": _("Partner Code must start with C."),
                }
            }
        partners = self.env["res.partner"].search([("ref", "=", code)], limit=2)
        if len(partners) == 1:
            self.partner_id = partners
        else:
            self.partner_id = False

    @api.constrains("partner_id", "partner_code")
    def _check_partner_code(self):
        for rec in self:
            code = (rec.partner_code or "").strip()
            # Keep existing agreements without a code valid. New values entered
            # through the form are validated strictly below.
            if not code:
                continue
            if not code.startswith("C"):
                raise ValidationError(_("Partner Code must start with C."))
            if not rec.partner_id or rec.partner_id.ref != code:
                raise ValidationError(
                    _("Partner Code must match the selected Partner.")
                )

    @api.depends("agreement_type_id")
    def _compute_domain(self):
        for rec in self:
            if rec.agreement_type_id and rec.agreement_type_id.domain:
                rec.domain = rec.agreement_type_id.domain
            else:
                rec.domain = "sale"

    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"[{rec.code}] {rec.name}"

    _sql_constraints = [
        (
            "code_partner_company_unique",
            "unique(code, commercial_partner_id, company_id)",
            "This agreement code already exists for this commercial entity!",
        )
    ]

    def copy(self, default=None):
        """Always assign a value for code because is required"""
        default = dict(default or {})
        if default.get("code", False):
            return super().copy(default)
        default.setdefault("code", _("%(code)s (copy)", code=self.code))
        return super().copy(default)
