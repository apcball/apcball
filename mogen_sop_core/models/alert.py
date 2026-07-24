from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError


class MogenSopAlert(models.Model):
    _name = "mogen.sop.alert"
    _description = "S&OP Alert"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "severity desc, id desc"
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
    alert_type = fields.Selection(
        [
            ("demand", "Demand"),
            ("supply", "Supply"),
            ("inventory", "Inventory"),
            ("capacity", "Capacity"),
            ("lead_time", "Lead Time"),
            ("cost", "Cost"),
            ("other", "Other"),
        ],
        required=True,
        default="other",
        tracking=True,
    )
    severity = fields.Selection(
        [
            ("info", "Information"),
            ("warning", "Warning"),
            ("critical", "Critical"),
        ],
        required=True,
        default="warning",
        index=True,
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
    message = fields.Text(required=True)
    state = fields.Selection(
        [
            ("open", "Open"),
            ("acknowledged", "Acknowledged"),
            ("resolved", "Resolved"),
        ],
        required=True,
        default="open",
        copy=False,
        index=True,
        tracking=True,
    )
    assigned_user_id = fields.Many2one(
        "res.users",
        string="Assigned To",
        check_company=True,
        tracking=True,
    )
    resolved_date = fields.Datetime(readonly=True, copy=False, tracking=True)

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
        plans = self.env["mogen.sop.plan"].browse(
            [values.get("plan_id") for values in vals_list if values.get("plan_id")]
        )
        self._check_locked_plans(plans)
        return super().create(vals_list)

    def write(self, values):
        plans = self.mapped("plan_id")
        if values.get("plan_id"):
            plans |= self.env["mogen.sop.plan"].browse(values["plan_id"])
        self._check_locked_plans(plans)
        return super().write(values)

    def unlink(self):
        self._check_locked_plans()
        return super().unlink()

    def action_acknowledge(self):
        if any(alert.state != "open" for alert in self):
            raise UserError(_("Only open alerts can be acknowledged."))
        self.write({"state": "acknowledged"})
        return True

    def action_resolve(self):
        if any(alert.state == "resolved" for alert in self):
            raise UserError(_("This alert is already resolved."))
        self.write(
            {
                "state": "resolved",
                "resolved_date": fields.Datetime.now(),
            }
        )
        return True
