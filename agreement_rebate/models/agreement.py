# Copyright 2020 Tecnativa - Carlos Dauden
# Copyright 2020 Tecnativa - Sergio Teruel
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import api, fields, models
from odoo.exceptions import UserError


class Agreement(models.Model):
    _inherit = "agreement"

    rebate_approval_state = fields.Selection(
        selection=[
            ("draft", "Draft"),
            ("submitted", "Submitted"),
            ("reviewed", "Reviewed"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
        ],
        string="Rebate approval status",
        default="draft",
        tracking=True,
        copy=False,
    )
    rebate_prepared_by_id = fields.Many2one(
        comodel_name="res.users",
        string="Prepared by",
        default=lambda self: self.env.user,
        readonly=True,
        tracking=True,
        copy=False,
    )
    rebate_reviewer_id = fields.Many2one(
        comodel_name="res.users", string="Reviewed by", readonly=True, copy=False
    )
    rebate_approver_id = fields.Many2one(
        comodel_name="res.users", string="Approved by", readonly=True, copy=False
    )
    rebate_submitted_at = fields.Datetime(readonly=True, copy=False)
    rebate_reviewed_at = fields.Datetime(readonly=True, copy=False)
    rebate_approved_at = fields.Datetime(readonly=True, copy=False)


    rebate_type = fields.Selection(
        selection=[
            ("global", "รวมทุกบรรทัด"),
            ("line", "แยกตามรายการสินค้า"),
            ("section_total", "คำนวณจากยอดรวมตามขั้นเปอร์เซ็นต์"),
            ("section_prorated", "คำนวณแยกตามช่วงยอดเงิน"),
        ],
        string="rebate type",
    )
    rebate_line_ids = fields.One2many(
        comodel_name="agreement.rebate.line",
        string="Agreement rebate lines",
        inverse_name="agreement_id",
        copy=True,
    )
    rebate_section_ids = fields.One2many(
        comodel_name="agreement.rebate.section",
        string="Agreement rebate sections",
        inverse_name="agreement_id",
        copy=True,
    )
    rebate_discount = fields.Float(digits="Discount", default=0.0)
    is_rebate = fields.Boolean(
        related="agreement_type_id.is_rebate", string="Is rebate agreement type"
    )
    additional_consumption = fields.Float(default=0.0)

    def _ensure_rebate_agreement(self):
        for agreement in self:
            if not agreement.is_rebate:
                raise UserError("Only rebate agreements can use this approval workflow.")

    def action_submit_rebate(self):
        self._ensure_rebate_agreement()
        for agreement in self:
            if agreement.rebate_approval_state not in ("draft", "rejected"):
                raise UserError("Only draft or rejected rebate agreements can be submitted.")
            agreement.write({
                "rebate_approval_state": "submitted",
                "rebate_prepared_by_id": self.env.user.id,
                "rebate_submitted_at": fields.Datetime.now(),
            })
        return True

    def action_review_rebate(self):
        self._ensure_rebate_agreement()
        if not self.env.user.has_group("agreement_rebate.group_rebate_reviewer"):
            raise UserError("You are not allowed to review rebate agreements.")
        for agreement in self:
            if agreement.rebate_approval_state != "submitted":
                raise UserError("Only submitted rebate agreements can be reviewed.")
            agreement.write({
                "rebate_approval_state": "reviewed",
                "rebate_reviewer_id": self.env.user.id,
                "rebate_reviewed_at": fields.Datetime.now(),
            })
        return True

    def action_approve_rebate(self):
        self._ensure_rebate_agreement()
        if not self.env.user.has_group("agreement_rebate.group_rebate_approver"):
            raise UserError("You are not allowed to approve rebate agreements.")
        for agreement in self:
            if agreement.rebate_approval_state != "reviewed":
                raise UserError("Only reviewed rebate agreements can be approved.")
            agreement.write({
                "rebate_approval_state": "approved",
                "rebate_approver_id": self.env.user.id,
                "rebate_approved_at": fields.Datetime.now(),
            })
        return True

    def action_reject_rebate(self):
        self._ensure_rebate_agreement()
        for agreement in self:
            if agreement.rebate_approval_state not in ("submitted", "reviewed"):
                raise UserError("Only submitted or reviewed rebate agreements can be rejected.")
            agreement.write({"rebate_approval_state": "rejected"})
        return True

    def action_reset_rebate(self):
        self._ensure_rebate_agreement()
        for agreement in self:
            agreement.write({
                "rebate_approval_state": "draft",
                "rebate_reviewer_id": False,
                "rebate_approver_id": False,
                "rebate_submitted_at": False,
                "rebate_reviewed_at": False,
                "rebate_approved_at": False,
            })
        return True



class AgreementRebateLine(models.Model):
    _name = "agreement.rebate.line"
    _description = "Agreement Rebate Lines"

    agreement_id = fields.Many2one(comodel_name="agreement", string="Agreement")
    rebate_target = fields.Selection(
        [
            ("product", "Product variant"),
            ("product_tmpl", "Product templates"),
            ("category", "Product categories"),
            ("condition", "Rebate condition"),
            ("domain", "Rebate domain"),
        ]
    )
    rebate_product_ids = fields.Many2many(
        comodel_name="product.product",
        string="Products",
    )
    rebate_product_tmpl_ids = fields.Many2many(
        comodel_name="product.template",
        string="Product templates",
    )
    rebate_category_ids = fields.Many2many(
        comodel_name="product.category",
        string="Product categories",
    )
    rebate_condition_id = fields.Many2one(
        comodel_name="agreement.rebate.condition",
        string="Rebate condition",
    )
    rebate_domain = fields.Char(
        compute="_compute_rebate_domain",
        store=True,
        readonly=False,
    )
    rebate_discount = fields.Float()

    @api.depends(
        "rebate_target",
        "rebate_product_ids",
        "rebate_product_tmpl_ids",
        "rebate_category_ids",
        "rebate_condition_id",
    )
    def _compute_rebate_domain(self):
        for line in self:
            rebate_domain = []
            if line.rebate_target == "product":
                rebate_domain = [("product_id", "in", line.rebate_product_ids.ids)]
            elif line.rebate_target == "product_tmpl":
                rebate_domain = [
                    (
                        "product_id.product_tmpl_id",
                        "in",
                        line.rebate_product_tmpl_ids.ids,
                    )
                ]
            elif line.rebate_target == "category":
                rebate_domain = [
                    ("product_id.categ_id", "in", line.rebate_category_ids.ids)
                ]
            elif line.rebate_target == "condition":
                rebate_domain = line.rebate_condition_id.rebate_domain or []
            line.rebate_domain = str(rebate_domain)


class AgreementRebateCondition(models.Model):
    _name = "agreement.rebate.condition"
    _description = "Agreement Rebate Condition"

    name = fields.Char(string="Rebate condition")
    rebate_domain = fields.Char(string="Domain")


class AgreementRebateSection(models.Model):
    _name = "agreement.rebate.section"
    _description = "Agreement Rebate Section"

    agreement_id = fields.Many2one(comodel_name="agreement", string="Agreement")
    amount_from = fields.Float(string="From")
    amount_to = fields.Float(string="To")
    rebate_discount = fields.Float(string="% Dto")
