from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class MogenSopPlan(models.Model):
    _name = "mogen.sop.plan"
    _description = "S&OP Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, code desc"
    _check_company_auto = True

    name = fields.Char(required=True, tracking=True)
    code = fields.Char(
        required=True,
        copy=False,
        default=lambda self: _("New"),
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
        tracking=True,
    )
    warehouse_ids = fields.Many2many(
        "stock.warehouse",
        string="Warehouses",
        check_company=True,
    )
    date_start = fields.Date(required=True, tracking=True)
    date_end = fields.Date(required=True, tracking=True)
    planning_granularity = fields.Selection(
        [("month", "Monthly"), ("week", "Weekly")],
        required=True,
        default="month",
        tracking=True,
    )
    scenario_id = fields.Many2one(
        "mogen.sop.scenario",
        check_company=True,
        tracking=True,
    )
    active_version_id = fields.Many2one(
        "mogen.sop.plan.version",
        string="Current Version",
        copy=False,
        tracking=True,
    )
    snapshot_date = fields.Datetime(copy=False, tracking=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("data_prepared", "Data Prepared"),
            ("review", "Review"),
            ("consensus", "Consensus"),
            ("approved", "Approved"),
            ("locked", "Locked"),
            ("cancelled", "Cancelled"),
        ],
        required=True,
        default="draft",
        copy=False,
        tracking=True,
        index=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Planner",
        default=lambda self: self.env.user,
        check_company=True,
        tracking=True,
    )
    manager_id = fields.Many2one(
        "res.users",
        check_company=True,
        tracking=True,
    )
    approved_by_id = fields.Many2one(
        "res.users",
        copy=False,
        readonly=True,
        check_company=True,
        tracking=True,
    )
    approved_date = fields.Datetime(copy=False, readonly=True, tracking=True)
    note = fields.Html()
    version_ids = fields.One2many(
        "mogen.sop.plan.version",
        "plan_id",
        string="Versions",
    )
    recommendation_ids = fields.One2many(
        "mogen.sop.recommendation",
        "plan_id",
        string="Recommendations",
    )
    alert_ids = fields.One2many(
        "mogen.sop.alert",
        "plan_id",
        string="Alerts",
    )
    demand_line_count = fields.Integer(compute="_compute_stat_counts")
    supply_line_count = fields.Integer(compute="_compute_stat_counts")
    inventory_health_count = fields.Integer(compute="_compute_stat_counts")
    recommendation_count = fields.Integer(compute="_compute_stat_counts")
    alert_count = fields.Integer(compute="_compute_stat_counts")
    version_count = fields.Integer(compute="_compute_stat_counts")

    _sql_constraints = [
        (
            "company_code_unique",
            "unique(company_id, code)",
            "The S&OP plan code must be unique per company.",
        ),
    ]

    @api.depends("version_ids", "recommendation_ids", "alert_ids")
    def _compute_stat_counts(self):
        for plan in self:
            plan.demand_line_count = 0
            plan.supply_line_count = 0
            plan.inventory_health_count = 0
            plan.recommendation_count = len(plan.recommendation_ids)
            plan.alert_count = len(plan.alert_ids)
            plan.version_count = len(plan.version_ids)

    @api.constrains("date_start", "date_end")
    def _check_date_range(self):
        for plan in self:
            if plan.date_start and plan.date_end and plan.date_end < plan.date_start:
                raise ValidationError(_("The end date must be on or after the start date."))

    @api.constrains("active_version_id", "scenario_id", "company_id")
    def _check_plan_relations(self):
        for plan in self:
            if (
                plan.active_version_id
                and plan.active_version_id.plan_id != plan
            ):
                raise ValidationError(
                    _("The current version must belong to the same S&OP plan.")
                )
            if plan.active_version_id and not plan.active_version_id.is_current:
                raise ValidationError(_("The active plan version must be current."))
            if plan.scenario_id and plan.scenario_id.company_id != plan.company_id:
                raise ValidationError(
                    _("The plan and its scenario must belong to the same company.")
                )

    @api.model_create_multi
    def create(self, vals_list):
        sequence = self.env["ir.sequence"]
        for values in vals_list:
            if values.get("state", "draft") != "draft":
                raise UserError(
                    _("New S&OP plans must start in Draft. Use workflow actions.")
                )
            if values.get("code", _("New")) == _("New"):
                values["code"] = (
                    sequence.with_company(values.get("company_id")).next_by_code(
                        "mogen.sop.plan"
                    )
                    or _("New")
                )
        return super().create(vals_list)

    def write(self, values):
        if "state" in values:
            raise UserError(_("Use the S&OP workflow actions to change plan state."))
        if (
            any(plan.state == "locked" for plan in self)
            and not self.env.user.has_group("mogen_sop_core.group_sop_admin")
        ):
            raise AccessError(_("Only an S&OP administrator can modify a locked plan."))
        return super().write(values)

    def _write_workflow_values(self, values):
        return super(MogenSopPlan, self).write(values)

    def unlink(self):
        if (
            any(plan.state == "locked" for plan in self)
            and not self.env.user.has_group("mogen_sop_core.group_sop_admin")
        ):
            raise AccessError(_("Only an S&OP administrator can delete a locked plan."))
        return super().unlink()

    def _transition(self, expected_state, target_state, extra_values=None):
        for plan in self:
            if plan.state != expected_state:
                raise UserError(
                    _(
                        "Plan %(plan)s must be in %(state)s before this action.",
                        plan=plan.display_name,
                        state=dict(plan._fields["state"].selection).get(expected_state),
                    )
                )
        values = {"state": target_state}
        values.update(extra_values or {})
        self._write_workflow_values(values)
        return True

    def _require_manager(self):
        if not self.env.user.has_group("mogen_sop_core.group_sop_manager"):
            raise AccessError(_("Only an S&OP manager can perform this action."))

    def action_prepare_data(self):
        return self._transition("draft", "data_prepared")

    def action_review(self):
        return self._transition("data_prepared", "review")

    def action_consensus(self):
        return self._transition("review", "consensus")

    def action_approve(self):
        self._require_manager()
        return self._transition(
            "consensus",
            "approved",
            {
                "approved_by_id": self.env.user.id,
                "approved_date": fields.Datetime.now(),
            },
        )

    def action_lock(self):
        self._require_manager()
        return self._transition("approved", "locked")

    def action_cancel(self):
        if any(plan.state == "locked" for plan in self):
            raise UserError(_("A locked plan cannot be cancelled."))
        if any(plan.state == "cancelled" for plan in self):
            raise UserError(_("This plan cannot be cancelled from its current state."))
        self._write_workflow_values({"state": "cancelled"})
        return True

    def action_reset_draft(self):
        self._require_manager()
        locked = self.filtered(lambda plan: plan.state == "locked")
        if locked and not self.env.user.has_group(
            "mogen_sop_core.group_sop_admin"
        ):
            raise AccessError(
                _("Only an S&OP administrator can reset a locked plan to draft.")
            )
        invalid = self.filtered(
            lambda plan: plan.state not in (
                "data_prepared",
                "review",
                "consensus",
                "cancelled",
                "locked",
            )
        )
        if invalid:
            raise UserError(_("Only pre-approved, cancelled, or locked plans can reset."))
        self._write_workflow_values(
            {
                "state": "draft",
                "approved_by_id": False,
                "approved_date": False,
            }
        )
        return True

    def action_create_version(self):
        self.ensure_one()
        if self.state == "locked" and not self.env.user.has_group(
            "mogen_sop_core.group_sop_admin"
        ):
            raise AccessError(
                _("Only an S&OP administrator can version a locked plan.")
            )
        Version = self.env["mogen.sop.plan.version"]
        current = self.active_version_id
        if not current:
            current = Version.search(
                [("plan_id", "=", self.id), ("is_current", "=", True)]
            )
        if current:
            current.write({"state": "archived", "is_current": False})
            current.flush_recordset(["state", "is_current"])
        latest = Version.search(
            [("plan_id", "=", self.id)],
            order="version_number desc",
            limit=1,
        )
        next_number = latest.version_number + 1 if latest else 1
        version = Version.create(
            {
                "plan_id": self.id,
                "version_number": next_number,
                "state": "current",
                "is_current": True,
            }
        )
        self.active_version_id = version
        return version

    def _stat_action(self, model_name):
        self.ensure_one()
        analytical_models = {
            "mogen.sop.recommendation",
            "mogen.sop.alert",
        }
        return {
            "type": "ir.actions.act_window",
            "name": self.display_name,
            "res_model": model_name,
            "view_mode": (
                "tree,form,pivot,graph"
                if model_name in analytical_models
                else "tree,form"
            ),
            "domain": [("plan_id", "=", self.id)],
            "context": {"default_plan_id": self.id},
        }

    def action_view_demand_lines(self):
        raise UserError(
            _("Demand Lines requires the mogen_sop_demand addon.")
        )

    def action_view_supply_lines(self):
        raise UserError(
            _("Supply Lines requires the mogen_sop_supply addon.")
        )

    def action_view_inventory_health(self):
        raise UserError(
            _("Inventory Health requires the mogen_sop_inventory addon.")
        )

    def action_view_recommendations(self):
        return self._stat_action("mogen.sop.recommendation")

    def action_view_alerts(self):
        return self._stat_action("mogen.sop.alert")

    def action_view_versions(self):
        return self._stat_action("mogen.sop.plan.version")


class MogenSopPlanVersion(models.Model):
    _name = "mogen.sop.plan.version"
    _description = "S&OP Plan Version"
    _order = "plan_id, version_number desc"
    _check_company_auto = True

    name = fields.Char(required=True)
    plan_id = fields.Many2one(
        "mogen.sop.plan",
        required=True,
        ondelete="cascade",
        index=True,
    )
    version_number = fields.Integer(required=True, readonly=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("current", "Current"),
            ("archived", "Archived"),
        ],
        required=True,
        default="draft",
        index=True,
    )
    created_by_id = fields.Many2one(
        "res.users",
        required=True,
        readonly=True,
        default=lambda self: self.env.user,
    )
    created_date = fields.Datetime(
        required=True,
        readonly=True,
        default=fields.Datetime.now,
    )
    note = fields.Html()
    is_current = fields.Boolean(default=False, index=True)

    _sql_constraints = [
        (
            "plan_version_number_unique",
            "unique(plan_id, version_number)",
            "The version number must be unique per plan.",
        ),
    ]

    def init(self):
        self.env.cr.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                mogen_sop_plan_version_one_current_idx
            ON mogen_sop_plan_version (plan_id)
            WHERE is_current
            """
        )

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            plan = self.env["mogen.sop.plan"].browse(values.get("plan_id"))
            if plan.state == "locked" and not self.env.user.has_group(
                "mogen_sop_core.group_sop_admin"
            ):
                raise AccessError(
                    _("Only an S&OP administrator can version a locked plan.")
                )
            if not values.get("version_number") and plan:
                values["version_number"] = (
                    max(plan.version_ids.mapped("version_number"), default=0) + 1
                )
            values.setdefault(
                "name",
                _(
                    "%(plan)s - Version %(number)s",
                    plan=plan.display_name,
                    number=values.get("version_number"),
                ),
            )
        versions = super().create(vals_list)
        for version in versions.filtered("is_current"):
            version.plan_id.active_version_id = version
        return versions

    def write(self, values):
        if (
            any(version.plan_id.state == "locked" for version in self)
            and not self.env.user.has_group("mogen_sop_core.group_sop_admin")
        ):
            raise AccessError(
                _("Only an S&OP administrator can modify a locked plan version.")
            )
        result = super().write(values)
        if {"state", "is_current"} & set(values):
            for version in self:
                if version.is_current:
                    version.plan_id.active_version_id = version
                elif version.plan_id.active_version_id == version:
                    version.plan_id.active_version_id = False
        return result

    def unlink(self):
        if (
            any(version.plan_id.state == "locked" for version in self)
            and not self.env.user.has_group("mogen_sop_core.group_sop_admin")
        ):
            raise AccessError(
                _("Only an S&OP administrator can delete a locked plan version.")
            )
        for version in self:
            if version.plan_id.active_version_id == version:
                version.plan_id.active_version_id = False
        return super().unlink()

    @api.constrains("state", "is_current")
    def _check_current_state(self):
        for version in self:
            if version.is_current != (version.state == "current"):
                raise ValidationError(
                    _("A current version must use the Current state, and vice versa.")
                )
