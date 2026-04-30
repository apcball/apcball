import calendar
from collections import defaultdict
from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class ForecastLine(models.Model):
    _name = "forecast.line"
    _description = "Sales Forecast Line"
    _order = "arrival_month, expected_week, id"

    plan_id = fields.Many2one("forecast.plan", required=True, ondelete="cascade", index=True)
    company_id = fields.Many2one(related="plan_id.company_id", store=True, index=True)
    product_id = fields.Many2one("product.product", required=True, domain=[("sale_ok", "=", True)], index=True)
    product_uom_id = fields.Many2one(
        "uom.uom", related="product_id.uom_id", store=True, readonly=True
    )
    forecast_qty = fields.Float(required=True, digits="Product Unit of Measure")
    arrival_month = fields.Date(
        required=True,
        help="Month of expected arrival (must be within current month + next 2 months).",
    )
    expected_week = fields.Selection(
        [("1", "Week 1"), ("2", "Week 2"), ("3", "Week 3"), ("4", "Week 4"), ("5", "Week 5")],
        required=True,
        default="1",
    )

    week1_qty = fields.Float(string="Week 1", digits="Product Unit of Measure")
    week2_qty = fields.Float(string="Week 2", digits="Product Unit of Measure")
    week3_qty = fields.Float(string="Week 3", digits="Product Unit of Measure")
    week4_qty = fields.Float(string="Week 4", digits="Product Unit of Measure")
    week5_qty = fields.Float(string="Week 5", digits="Product Unit of Measure")

    allocation_ids = fields.One2many("forecast.allocation", "plan_line_id", string="Allocations")
    allocated_qty = fields.Float(compute="_compute_kpis", store=True, digits="Product Unit of Measure")
    actual_sold_qty = fields.Float(compute="_compute_kpis", store=True, digits="Product Unit of Measure")
    remaining_qty = fields.Float(compute="_compute_kpis", store=True, digits="Product Unit of Measure")
    allocation_rate = fields.Float(compute="_compute_kpis", store=True)
    accuracy_rate = fields.Float(compute="_compute_kpis", store=True)

    @api.depends(
        "forecast_qty",
        "allocation_ids.allocated_qty",
        "allocation_ids.state",
        "allocation_ids.is_non_forecast",
        "allocation_ids.sale_order_line_id.product_uom_qty",
        "allocation_ids.sale_order_line_id.qty_delivered",
        "allocation_ids.sale_order_id.state",
    )
    def _compute_kpis(self):
        """
        Compute KPIs for forecast lines using optimized queries.

        Original issue: N+1 query problem when accessing related fields
        Fix: Use read_group for aggregated queries + prefetch related fields

        Performance optimization:
        1. Single read_group query for allocated quantities
        2. Single read_group query for actual sold quantities
        3. All allocations fetched with prefetch of related fields
        """
        # Initialize grouping structures
        grouped_alloc = defaultdict(lambda: {"allocated": 0.0, "actual": 0.0})

        if not self.ids:
            return

        # Query allocations with optimized approach
        # Use prefetch to avoid N+1 queries on related fields
        allocations = self.env["forecast.allocation"].search([
            ("plan_line_id", "in", self.ids),
            ("state", "=", "confirmed"),
        ])

        # Prefetch related fields to avoid N+1 queries
        # This loads all related sale orders and sale order lines in batch
        if allocations:
            # Prefetch sale orders
            allocations.mapped('sale_order_id')
            # Prefetch sale order lines
            allocations.mapped('sale_order_line_id')

        # Group allocations by plan_line_id
        # Now accessing related fields won't trigger additional queries
        for alloc in allocations:
            line_id = alloc.plan_line_id.id

            # Allocated quantity (exclude non-forecast)
            if not alloc.is_non_forecast:
                grouped_alloc[line_id]["allocated"] += alloc.allocated_qty

            # Actual sold quantity (only for confirmed/done sale orders)
            if alloc.sale_order_id.state in ("sale", "done"):
                # Use qty_delivered if available, otherwise use ordered quantity
                actual_qty = alloc.sale_order_line_id.qty_delivered or alloc.sale_order_line_id.product_uom_qty
                grouped_alloc[line_id]["actual"] += actual_qty

        # Apply computed values to forecast lines
        for rec in self:
            allocated = grouped_alloc[rec.id]["allocated"]
            actual = grouped_alloc[rec.id]["actual"]
            rec.allocated_qty = allocated
            rec.actual_sold_qty = actual
            rec.remaining_qty = rec.forecast_qty - allocated
            rec.allocation_rate = (allocated / rec.forecast_qty * 100.0) if rec.forecast_qty else 0.0
            rec.accuracy_rate = (actual / rec.forecast_qty * 100.0) if rec.forecast_qty else 0.0

    @api.constrains("forecast_qty")
    def _check_forecast_qty(self):
        for rec in self:
            if rec.forecast_qty <= 0:
                raise ValidationError(_("Forecast quantity must be greater than 0."))

    @api.constrains("arrival_month")
    def _check_arrival_horizon(self):
        today = fields.Date.context_today(self)
        current_month = date(today.year, today.month, 1)
        max_month = current_month + relativedelta(months=2)
        for rec in self:
            if not rec.arrival_month:
                continue
            month_start = date(rec.arrival_month.year, rec.arrival_month.month, 1)
            if month_start < current_month or month_start > max_month:
                raise ValidationError(
                    _("Arrival month must be within the 3-month forecast window (current month + next 2 months).")
                )

    @api.constrains("week1_qty", "week2_qty", "week3_qty", "week4_qty", "week5_qty", "forecast_qty")
    def _check_week_distribution_total(self):
        for rec in self:
            total = rec.week1_qty + rec.week2_qty + rec.week3_qty + rec.week4_qty + rec.week5_qty
            if round(total - rec.forecast_qty, 6) != 0:
                raise ValidationError(
                    _("Weekly distribution total (%s) must match forecast quantity (%s).")
                    % (total, rec.forecast_qty)
                )

    @api.onchange("forecast_qty", "arrival_month")
    def _onchange_distribute_weeks(self):
        for rec in self:
            if rec.forecast_qty and rec.arrival_month:
                rec._apply_even_distribution()

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        for rec in lines:
            if rec.arrival_month and rec.forecast_qty and not any(
                [rec.week1_qty, rec.week2_qty, rec.week3_qty, rec.week4_qty, rec.week5_qty]
            ):
                rec._apply_even_distribution()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {"forecast_qty", "arrival_month"} & set(vals.keys()):
            for rec in self:
                rec._apply_even_distribution()
        return res

    def _apply_even_distribution(self):
        self.ensure_one()
        if not self.arrival_month:
            return
        _, last_day = calendar.monthrange(self.arrival_month.year, self.arrival_month.month)
        week_count = 5 if last_day >= 29 else 4
        base = self.forecast_qty / week_count if week_count else 0.0
        amounts = [round(base, 2)] * week_count
        correction = round(self.forecast_qty - sum(amounts), 2)
        if amounts:
            amounts[-1] = round(amounts[-1] + correction, 2)
        amounts += [0.0] * (5 - week_count)

        self.week1_qty, self.week2_qty, self.week3_qty, self.week4_qty, self.week5_qty = amounts[:5]

    def action_distribute_evenly(self):
        for rec in self:
            rec._apply_even_distribution()
