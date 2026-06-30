from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class SalePerformanceTarget(models.Model):
    _name = "buz.sales.performance.target"
    _description = "Sales Performance Target"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"
    _rec_name = "display_name"

    # ------------------------------------------------------------------
    # Identity / ownership
    # ------------------------------------------------------------------
    company_id = fields.Many2one(
        "res.company", string="Company", required=True, index=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(
        related="company_id.currency_id", string="Currency", store=True, readonly=True,
    )
    name = fields.Char(string="Description", required=True, tracking=True)
    display_name = fields.Char(
        string="Display Name", compute="_compute_display_name", store=True,
    )
    user_id = fields.Many2one(
        "res.users", string="Salesperson", index=True, tracking=True,
    )
    team_id = fields.Many2one(
        "crm.team", string="Sales Team", index=True, tracking=True,
    )
    responsible_id = fields.Many2one(
        "res.users", string="Responsible", compute="_compute_responsible", store=True,
    )

    # ------------------------------------------------------------------
    # Target configuration
    # ------------------------------------------------------------------
    target_type = fields.Selection(
        [
            ("company", "Company"),
            ("team", "Sales Team"),
            ("person", "Salesperson"),
        ],
        string="Target Type", required=True, default="person", tracking=True,
    )
    target_amount = fields.Monetary(
        string="Target Amount", required=True, currency_field="currency_id", tracking=True,
    )
    period = fields.Selection(
        [
            ("daily", "Daily"),
            ("monthly", "Monthly"),
            ("quarterly", "Quarterly"),
            ("yearly", "Yearly"),
        ],
        string="Period", required=True, default="monthly", tracking=True,
    )

    # ------------------------------------------------------------------
    # Date range
    # ------------------------------------------------------------------
    date_start = fields.Date(string="Start Date", required=True, tracking=True)
    date_end = fields.Date(string="End Date", required=True, tracking=True)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("confirmed", "Confirmed"),
            ("closed", "Closed"),
        ],
        string="State", default="draft", tracking=True,
    )

    # ------------------------------------------------------------------
    # Achievement (read from buz.sales.performance.result - O(log n))
    # ------------------------------------------------------------------
    achieved_amount = fields.Monetary(
        string="Actual Sales", compute="_compute_achievement",
        currency_field="currency_id",
    )
    refund_amount = fields.Monetary(
        string="Refund Amount", compute="_compute_achievement",
        currency_field="currency_id",
    )
    invoice_amount = fields.Monetary(
        string="Invoice Amount", compute="_compute_achievement",
        currency_field="currency_id",
    )
    remaining_amount = fields.Monetary(
        string="Remaining", compute="_compute_achievement",
        currency_field="currency_id",
    )
    achievement_pct = fields.Float(
        string="Achievement %", compute="_compute_achievement",
        group_operator="avg",
    )
    avg_daily_sales = fields.Monetary(
        string="Avg Daily Sales", compute="_compute_achievement",
        currency_field="currency_id",
    )

    # ------------------------------------------------------------------
    # Theoretical tracking
    # ------------------------------------------------------------------
    theoretical_amount = fields.Monetary(
        string="Theoretical Target", compute="_compute_theoretical",
        currency_field="currency_id",
    )
    theoretical_pct = fields.Float(
        string="Theoretical %", compute="_compute_theoretical",
    )
    theoretical_status = fields.Selection(
        [
            ("above", "Above Target"),
            ("on_track", "On Track"),
            ("below", "Below Target"),
        ],
        string="Theoretical Status", compute="_compute_theoretical",
    )
    forecast_amount = fields.Monetary(
        string="Forecast", compute="_compute_theoretical",
        currency_field="currency_id",
        help="Linear projection of current achievement to the end date.",
    )

    # ------------------------------------------------------------------
    # Smart counters
    # ------------------------------------------------------------------
    result_line_count = fields.Integer(
        string="Recognized Lines", compute="_compute_counters",
    )
    sale_order_count = fields.Integer(
        string="Sale Orders", compute="_compute_counters",
    )

    note = fields.Text(string="Notes")

    _sql_constraints = [
        (
            "check_target_amount_positive",
            "CHECK(target_amount > 0)",
            "Target amount must be positive.",
        ),
        (
            "check_dates_consistency",
            "CHECK(date_start <= date_end)",
            "Start date must be before or equal to end date.",
        ),
    ]

    # ==================================================================
    # Computes
    # ==================================================================
    @api.depends("name", "user_id", "team_id", "date_start", "date_end", "period")
    def _compute_display_name(self):
        for rec in self:
            parts = [rec.name] if rec.name else []
            if rec.target_type == "person" and rec.user_id:
                parts.append("(%s)" % rec.user_id.name)
            elif rec.target_type == "team" and rec.team_id:
                parts.append("(%s)" % rec.team_id.name)
            elif rec.target_type == "company":
                parts.append("(%s)" % rec.company_id.name)
            if rec.date_start and rec.date_end:
                parts.append("[%s → %s]" % (rec.date_start, rec.date_end))
            rec.display_name = " ".join(parts) or _("Sales Target")

    @api.depends("user_id", "team_id", "target_type")
    def _compute_responsible(self):
        for rec in self:
            if rec.target_type == "person" and rec.user_id:
                rec.responsible_id = rec.user_id
            elif rec.target_type == "team" and rec.team_id and rec.team_id.user_id:
                rec.responsible_id = rec.team_id.user_id
            else:
                rec.responsible_id = self.env.user

    @api.depends("date_start", "date_end", "company_id", "user_id", "team_id", "target_type")
    def _compute_achievement(self):
        Result = self.env["buz.sales.performance.result"].sudo()
        for rec in self:
            if not rec.date_start or not rec.date_end:
                rec.update({
                    "achieved_amount": 0.0, "refund_amount": 0.0,
                    "invoice_amount": 0.0, "remaining_amount": rec.target_amount,
                    "achievement_pct": 0.0, "avg_daily_sales": 0.0,
                })
                continue
            domain = rec._result_domain()
            agg = Result.read_group(domain, ["net_sales:sum", "invoice_amount:sum", "refund_amount:sum"], [])[0]
            net = agg["net_sales"] or 0.0
            inv = agg["invoice_amount"] or 0.0
            ref = agg["refund_amount"] or 0.0
            days = max(1, (rec.date_end - rec.date_start).days + 1)
            rec.update({
                "achieved_amount": net,
                "invoice_amount": inv,
                "refund_amount": ref,
                "remaining_amount": max(0.0, rec.target_amount - net),
                "achievement_pct": (net / rec.target_amount) if rec.target_amount else 0.0,
                "avg_daily_sales": net / days,
            })

    @api.depends("target_amount", "date_start", "date_end", "achieved_amount")
    def _compute_theoretical(self):
        today = fields.Date.context_today(self)
        for rec in self:
            if not rec.date_start or not rec.date_end or not rec.target_amount:
                rec.update({
                    "theoretical_amount": 0.0, "theoretical_pct": 0.0,
                    "theoretical_status": "below", "forecast_amount": 0.0,
                })
                continue
            total_days = (rec.date_end - rec.date_start).days + 1
            if today <= rec.date_start:
                elapsed = 0
            elif today >= rec.date_end:
                elapsed = total_days
            else:
                elapsed = (today - rec.date_start).days + 1
            time_ratio = elapsed / total_days if total_days > 0 else 0.0
            theo = rec.target_amount * time_ratio
            rec.theoretical_amount = theo
            rec.theoretical_pct = time_ratio
            if rec.achieved_amount >= rec.target_amount:
                status = "above"
            elif rec.achieved_amount >= theo:
                status = "on_track"
            else:
                status = "below"
            rec.theoretical_status = status
            # Linear forecast: project current daily run-rate to end of period.
            daily_rate = rec.achieved_amount / elapsed if elapsed > 0 else 0.0
            rec.forecast_amount = daily_rate * total_days

    @api.depends("date_start", "date_end", "company_id", "user_id", "team_id", "target_type")
    def _compute_counters(self):
        Result = self.env["buz.sales.performance.result"].sudo()
        for rec in self:
            if not rec.date_start or not rec.date_end:
                rec.result_line_count = 0
                rec.sale_order_count = 0
                continue
            domain = rec._result_domain()
            rec.result_line_count = Result.search_count(domain)
            rows = Result.read_group(domain, ["sale_order_id"], ["sale_order_id"])
            rec.sale_order_count = len(rows)

    # ==================================================================
    # Domains / helpers
    # ==================================================================
    def _result_domain(self):
        """Domain on buz.sales.performance.result matching this target scope."""
        self.ensure_one()
        domain = [
            ("company_id", "=", self.company_id.id),
            ("date_invoiced", ">=", fields.Datetime.to_datetime(self.date_start)),
            ("date_invoiced", "<=", fields.Datetime.to_datetime(self.date_end) + relativedelta(days=1) - relativedelta(seconds=1)),
        ]
        if self.target_type == "person" and self.user_id:
            domain.append(("salesperson_id", "=", self.user_id.id))
        elif self.target_type == "team" and self.team_id:
            domain.append(("team_id", "=", self.team_id.id))
        return domain

    @api.onchange("target_type")
    def _onchange_target_type(self):
        if self.target_type != "person":
            self.user_id = False
        if self.target_type != "team":
            self.team_id = False

    @api.onchange("period")
    def _onchange_period(self):
        if not self.period:
            return
        today = fields.Date.context_today(self)
        if self.period == "daily":
            self.date_start = self.date_end = today
        elif self.period == "monthly":
            self.date_start = today.replace(day=1)
            self.date_end = today + relativedelta(day=1, months=1, days=-1)
        elif self.period == "quarterly":
            q = (today.month - 1) // 3 + 1
            self.date_start = today.replace(month=(q - 1) * 3 + 1, day=1)
            self.date_end = self.date_start + relativedelta(months=3, days=-1)
        elif self.period == "yearly":
            self.date_start = today.replace(month=1, day=1)
            self.date_end = today.replace(month=12, day=31)

    # ==================================================================
    # Workflow
    # ==================================================================
    def action_confirm(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(_("Only draft targets can be confirmed."))
            rec.state = "confirmed"
            rec.message_post(body=_("Target confirmed."))

    def action_close(self):
        for rec in self:
            if rec.state != "confirmed":
                raise UserError(_("Only confirmed targets can be closed."))
            rec.state = "closed"
            rec.message_post(body=_("Target closed."))

    def action_reset_to_draft(self):
        for rec in self:
            if rec.state not in ("confirmed", "closed"):
                raise UserError(_("Only confirmed or closed targets can be reset."))
            rec.state = "draft"
            rec.message_post(body=_("Target reset to draft."))

    def action_view_results(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Performance Results"),
            "res_model": "buz.sales.performance.result",
            "view_mode": "tree,pivot,graph,form",
            "domain": self._result_domain(),
            "context": {
                "default_company_id": self.company_id.id,
                "search_default_groupby_salesperson_id": 1,
            },
        }

    # ==================================================================
    # Constraints
    # ==================================================================
    @api.constrains("target_type", "user_id", "team_id")
    def _check_type_subject(self):
        for rec in self:
            if rec.target_type == "person" and not rec.user_id:
                raise ValidationError(_("Individual target requires a Salesperson."))
            if rec.target_type == "team" and not rec.team_id:
                raise ValidationError(_("Team target requires a Sales Team."))

    @api.constrains("target_type", "user_id", "team_id")
    def _check_exclusive_subject(self):
        for rec in self:
            if rec.target_type == "person" and rec.team_id:
                raise ValidationError(_("Individual target cannot have a Sales Team."))
            if rec.target_type == "team" and rec.user_id:
                raise ValidationError(_("Team target cannot have a Salesperson."))

    # ==================================================================
    # Cron
    # ==================================================================
    @api.model
    def _cron_notify_achievements(self):
        """Notify responsible users on target completion / off-track status."""
        targets = self.search([
            ("state", "=", "confirmed"),
            ("date_end", ">=", fields.Date.context_today(self)),
        ])
        for target in targets:
            target._compute_achievement()
            target._compute_theoretical()
            if target.achievement_pct >= 1.0 or target.theoretical_status == "below":
                template = self.env.ref(
                    "buz_sales_performance_engine.email_template_target_notification",
                    raise_if_not_found=False,
                )
                if template:
                    template.send_mail(target.id, force_send=False)
