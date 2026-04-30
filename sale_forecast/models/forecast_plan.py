from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ForecastPlan(models.Model):
    _name = "forecast.plan"
    _description = "Sales Forecast Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "start_date desc, id desc"
    _sql_constraints = [
        (
            "forecast_plan_user_month_company_uniq",
            "unique(user_id, start_date, company_id)",
            "Only one forecast plan is allowed per user per month.",
        )
    ]

    name = fields.Char(
        string="Plan Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
        tracking=True,
    )
    user_id = fields.Many2one(
        "res.users",
        string="Salesperson",
        required=True,
        default=lambda self: self.env.user,
        index=True,
        tracking=True,
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("done", "Done"),
            ("cancel", "Cancelled"),
        ],
        default="draft",
        tracking=True,
    )
    start_date = fields.Date(
        string="Forecast Start Date",
        required=True,
        default=lambda self: fields.Date.start_of(fields.Date.context_today(self), "month"),
        tracking=True,
    )
    end_date = fields.Date(string="Forecast End Date", compute="_compute_end_date", store=True)
    blanket_reference = fields.Char(string="Blanket PO Reference")
    company_id = fields.Many2one(
        "res.company", default=lambda self: self.env.company, required=True, index=True
    )
    line_ids = fields.One2many("forecast.line", "plan_id", string="Forecast Lines")

    total_forecast_qty = fields.Float(compute="_compute_totals", store=True)
    total_allocated_qty = fields.Float(compute="_compute_totals", store=True)
    total_actual_sold_qty = fields.Float(compute="_compute_totals", store=True)
    allocation_rate = fields.Float(string="Allocation Rate (%)", compute="_compute_totals", store=True)
    accuracy_rate = fields.Float(string="Forecast Accuracy (%)", compute="_compute_totals", store=True)

    @api.depends("start_date")
    def _compute_end_date(self):
        for rec in self:
            rec.end_date = rec.start_date + relativedelta(months=3, days=-1) if rec.start_date else False

    @api.depends(
        "line_ids.forecast_qty",
        "line_ids.allocated_qty",
        "line_ids.actual_sold_qty",
    )
    def _compute_totals(self):
        for rec in self:
            forecast = sum(rec.line_ids.mapped("forecast_qty"))
            allocated = sum(rec.line_ids.mapped("allocated_qty"))
            actual = sum(rec.line_ids.mapped("actual_sold_qty"))
            rec.total_forecast_qty = forecast
            rec.total_allocated_qty = allocated
            rec.total_actual_sold_qty = actual
            rec.allocation_rate = (allocated / forecast * 100.0) if forecast else 0.0
            rec.accuracy_rate = (actual / forecast * 100.0) if forecast else 0.0

    @api.constrains("start_date")
    def _check_start_date_month(self):
        for rec in self:
            if rec.start_date and rec.start_date != fields.Date.start_of(rec.start_date, "month"):
                raise ValidationError(_("Forecast Start Date must be the first day of a month."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("forecast.plan") or _("New")
            vals.setdefault("user_id", self.env.user.id)
        return super().create(vals_list)

    def action_confirm(self):
        self.write({"state": "confirmed"})

    def action_done(self):
        self.write({"state": "done"})

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_set_draft(self):
        self.write({"state": "draft"})

    def action_distribute_weekly(self):
        for plan in self:
            plan.line_ids.action_distribute_evenly()

    def action_view_lines_analysis(self):
        self.ensure_one()
        action = self.env.ref("sale_forecast.action_forecast_line_analysis").read()[0]
        action["domain"] = [("plan_id", "=", self.id)]
        return action
