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
    rebate_discount = fields.Float(
        string="Rebate Discount (%)", digits=(16, 2), default=0.0
    )
    is_rebate = fields.Boolean(
        related="agreement_type_id.is_rebate", string="Is rebate agreement type"
    )
    additional_consumption = fields.Float(default=0.0)

    def _ensure_rebate_agreement(self):
        for agreement in self:
            if not agreement.is_rebate:
                raise UserError("Only rebate agreements can use this approval workflow.")

    def _get_rebate_locked_fields(self):
        """Business fields that cannot be changed while the agreement is approved."""
        return [
            "partner_id",
            "agreement_type_id",
            "domain",
            "signature_date",
            "start_date",
            "end_date",
            "rebate_type",
            "rebate_discount",
            "rebate_line_ids",
            "rebate_section_ids",
        ]

    def _get_rebate_approval_fields(self):
        return [
            "rebate_approval_state",
            "rebate_prepared_by_id",
            "rebate_reviewer_id",
            "rebate_approver_id",
            "rebate_submitted_at",
            "rebate_reviewed_at",
            "rebate_approved_at",
        ]

    def write(self, vals):
        for agreement in self:
            if agreement.rebate_approval_state != "approved":
                continue
            locked_fields = set(vals) & set(self._get_rebate_locked_fields())
            if locked_fields:
                raise UserError(
                    "You cannot modify the business data of an approved rebate "
                    "agreement (%s). Reset the agreement to draft first."
                    % agreement.display_name
                )
            approval_fields = set(vals) & set(self._get_rebate_approval_fields())
            if approval_fields and not self.env.context.get(
                "agreement_rebate_reset"
            ):
                raise UserError(
                    "You cannot change the approval data of an approved rebate "
                    "agreement (%s) directly. Use the Reset action instead."
                    % agreement.display_name
                )
        return super().write(vals)

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
        # Internal context: allows only the approval state/data changes of the
        # reset action. Business fields stay locked for approved agreements even
        # when this context flag is forged through RPC/Import.
        self = self.with_context(agreement_rebate_reset=True)
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
    rebate_discount = fields.Float(string="Rebate Discount (%)", digits=(16, 2))

    def _check_agreement_not_approved(self):
        for line in self:
            if line.agreement_id.rebate_approval_state == "approved":
                raise UserError(
                    "You cannot modify the rebate lines of an approved agreement "
                    "(%s). Reset the agreement to draft first."
                    % line.agreement_id.display_name
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("agreement_id"):
                agreement = self.env["agreement"].browse(vals["agreement_id"])
                if agreement.rebate_approval_state == "approved":
                    raise UserError(
                        "You cannot add rebate lines to an approved agreement "
                        "(%s). Reset the agreement to draft first."
                        % agreement.display_name
                    )
        return super().create(vals_list)

    def write(self, vals):
        self._check_agreement_not_approved()
        return super().write(vals)

    def unlink(self):
        self._check_agreement_not_approved()
        return super().unlink()

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
    rebate_discount = fields.Float(string="Rebate Discount (%)", digits=(16, 2))

    def _check_agreement_not_approved(self):
        for section in self:
            if section.agreement_id.rebate_approval_state == "approved":
                raise UserError(
                    "You cannot modify the rebate sections of an approved "
                    "agreement (%s). Reset the agreement to draft first."
                    % section.agreement_id.display_name
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("agreement_id"):
                agreement = self.env["agreement"].browse(vals["agreement_id"])
                if agreement.rebate_approval_state == "approved":
                    raise UserError(
                        "You cannot add rebate sections to an approved agreement "
                        "(%s). Reset the agreement to draft first."
                        % agreement.display_name
                    )
        return super().create(vals_list)

    def write(self, vals):
        self._check_agreement_not_approved()
        return super().write(vals)

    def unlink(self):
        self._check_agreement_not_approved()
        return super().unlink()
