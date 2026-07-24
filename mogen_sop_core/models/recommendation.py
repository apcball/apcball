from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class MogenSopRecommendation(models.Model):
    _name = "mogen.sop.recommendation"
    _description = "S&OP Recommendation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "priority, required_date, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    plan_id = fields.Many2one(
        "mogen.sop.plan",
        required=True,
        ondelete="cascade",
        check_company=True,
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        related="plan_id.company_id",
        store=True,
        readonly=True,
        index=True,
    )
    recommendation_type = fields.Selection(
        [
            ("purchase", "Purchase"),
            ("manufacture", "Manufacture"),
            ("transfer", "Transfer"),
            ("forecast_adjustment", "Forecast Adjustment"),
            ("warning", "Warning"),
        ],
        required=True,
        tracking=True,
    )
    product_id = fields.Many2one(
        "product.product",
        check_company=True,
        tracking=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        check_company=True,
        tracking=True,
    )
    quantity = fields.Float()
    required_date = fields.Date()
    priority = fields.Selection(
        [
            ("0", "Low"),
            ("1", "Normal"),
            ("2", "High"),
            ("3", "Urgent"),
        ],
        required=True,
        default="1",
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("reviewed", "Reviewed"),
            ("approved", "Approved"),
            ("rejected", "Rejected"),
            ("executed", "Executed"),
        ],
        required=True,
        default="draft",
        copy=False,
        index=True,
        tracking=True,
    )
    reason = fields.Text()
    impact = fields.Text()
    source_model = fields.Char(readonly=True)
    source_res_id = fields.Integer(readonly=True)
    purchase_order_id = fields.Many2one(
        "purchase.order",
        readonly=True,
        copy=False,
        check_company=True,
    )
    manufacturing_order_id = fields.Many2one(
        "mrp.production",
        readonly=True,
        copy=False,
        check_company=True,
    )
    approved_by_id = fields.Many2one(
        "res.users",
        readonly=True,
        copy=False,
        check_company=True,
        tracking=True,
    )
    approved_date = fields.Datetime(readonly=True, copy=False, tracking=True)

    def _check_locked_plans(self, plans=None):
        plans = plans or self.mapped("plan_id")
        if (
            any(plan.state == "locked" for plan in plans)
            and not self.env.user.has_group("mogen_sop_core.group_sop_admin")
        ):
            raise AccessError(
                _("Only an S&OP administrator can change a locked plan's documents.")
            )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("state", "draft") != "draft":
                raise UserError(
                    _("New recommendations must start in Draft. Use workflow actions.")
                )
        plans = self.env["mogen.sop.plan"].browse(
            [values.get("plan_id") for values in vals_list if values.get("plan_id")]
        )
        self._check_locked_plans(plans)
        return super().create(vals_list)

    def write(self, values):
        if "state" in values:
            raise UserError(
                _("Use recommendation workflow actions to change its state.")
            )
        plans = self.mapped("plan_id")
        if values.get("plan_id"):
            plans |= self.env["mogen.sop.plan"].browse(values["plan_id"])
        self._check_locked_plans(plans)
        return super().write(values)

    def _write_workflow_values(self, values):
        self._check_locked_plans()
        return super(MogenSopRecommendation, self).write(values)

    def unlink(self):
        self._check_locked_plans()
        return super().unlink()

    def _require_manager(self):
        if not self.env.user.has_group("mogen_sop_core.group_sop_manager"):
            raise AccessError(_("Only an S&OP manager can perform this action."))

    def action_approve(self):
        self._require_manager()
        if any(recommendation.state not in ("draft", "reviewed") for recommendation in self):
            raise UserError(
                _("Only draft or reviewed recommendations can be approved.")
            )
        self._write_workflow_values(
            {
                "state": "approved",
                "approved_by_id": self.env.user.id,
                "approved_date": fields.Datetime.now(),
            }
        )
        return True

    def action_reject(self):
        self._require_manager()
        if any(recommendation.state == "executed" for recommendation in self):
            raise UserError(_("An executed recommendation cannot be rejected."))
        self._write_workflow_values(
            {
                "state": "rejected",
                "approved_by_id": False,
                "approved_date": False,
            }
        )
        return True
