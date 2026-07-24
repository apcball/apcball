import json
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from ..services.forecast_math import ForecastMath


class MogenSopForecastModel(models.Model):
    _name = "mogen.sop.forecast.model"
    _description = "S&OP Forecast Model"
    _order = "company_id, code"
    _check_company_auto = True

    name = fields.Char(required=True)
    code = fields.Char(required=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    model_type = fields.Selection([
        ("moving_average", "Simple Moving Average"),
        ("weighted_moving_average", "Weighted Moving Average"),
        ("exponential_smoothing", "Single Exponential Smoothing"),
        ("linear_trend", "Linear Trend"),
        ("seasonal_naive", "Seasonal Naive"),
        ("same_period_last_year", "Same Period Last Year"),
        ("croston", "Croston"),
    ], required=True, index=True)
    active = fields.Boolean(default=True)
    history_periods = fields.Integer(default=6, required=True)
    alpha = fields.Float(default=0.2)
    beta = fields.Float(default=0.0)
    gamma = fields.Float(default=0.0)
    seasonal_periods = fields.Integer(default=12)
    weight_config = fields.Text(default="[]")
    minimum_history_points = fields.Integer(default=3, required=True)
    support_intermittent_demand = fields.Boolean(default=False)
    description = fields.Text()
    algorithm_version = fields.Char(default="1.0", required=True)

    _sql_constraints = [("forecast_model_company_code_unique", "unique(company_id, code)", "Forecast model code must be unique per company.")]

    @api.constrains("history_periods", "minimum_history_points", "seasonal_periods", "alpha")
    def _check_parameters(self):
        for record in self:
            if record.history_periods < 1 or record.minimum_history_points < 1 or record.seasonal_periods < 1:
                raise ValidationError(_("Forecast periods must be positive."))
            if record.model_type in ("exponential_smoothing", "croston") and not 0 < record.alpha <= 1:
                raise ValidationError(_("Alpha must be between zero and one."))

    def _weights(self):
        self.ensure_one()
        try:
            weights = json.loads(self.weight_config or "[]")
        except json.JSONDecodeError as error:
            raise ValidationError(_("Weight configuration must be a JSON array.")) from error
        if not isinstance(weights, list) or not all(isinstance(value, (int, float)) and value >= 0 for value in weights):
            raise ValidationError(_("Weight configuration must contain non-negative numbers."))
        return [float(value) for value in weights]

    def calculate(self, history):
        self.ensure_one()
        values = [float(value) for value in history[-self.history_periods:]]
        if len(values) < self.minimum_history_points:
            return None, "insufficient_history"
        methods = {
            "moving_average": lambda: ForecastMath.moving_average(values, min(self.history_periods, len(values))),
            "weighted_moving_average": lambda: ForecastMath.weighted_moving_average(values, self._weights()),
            "exponential_smoothing": lambda: ForecastMath.exponential_smoothing(values, self.alpha),
            "linear_trend": lambda: ForecastMath.linear_trend(values),
            "seasonal_naive": lambda: ForecastMath.seasonal_naive(values, self.seasonal_periods),
            "same_period_last_year": lambda: ForecastMath.same_period_last_year(values, self.seasonal_periods),
            "croston": lambda: ForecastMath.croston(values, self.alpha),
        }
        value = methods[self.model_type]()
        return value, False if value is not None else "invalid_parameters"


class MogenSopForecastRun(models.Model):
    _name = "mogen.sop.forecast.run"
    _description = "S&OP Forecast Run"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("New"), tracking=True)
    sop_plan_id = fields.Many2one("mogen.sop.plan", required=True, check_company=True, index=True)
    version_id = fields.Many2one("mogen.sop.plan.version", index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    warehouse_ids = fields.Many2many("stock.warehouse", check_company=True)
    date_start = fields.Date(required=True, index=True)
    date_end = fields.Date(required=True, index=True)
    history_date_start = fields.Date(required=True, index=True)
    history_date_end = fields.Date(required=True, index=True)
    forecast_horizon = fields.Integer(default=1, required=True)
    granularity = fields.Selection([("week", "Weekly"), ("month", "Monthly")], required=True, default="month")
    state = fields.Selection([("draft", "Draft"), ("queued", "Queued"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed"), ("cancelled", "Cancelled")], default="draft", required=True, tracking=True, index=True)
    model_ids = fields.Many2many("mogen.sop.forecast.model", check_company=True)
    result_ids = fields.One2many("mogen.sop.forecast.result", "forecast_run_id")
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    error_message = fields.Text(readonly=True)
    calculation_log = fields.Text(readonly=True)
    data_snapshot_date = fields.Datetime(readonly=True, index=True)
    timezone = fields.Char(default=lambda self: self.env.user.tz or "UTC", required=True)
    requested_by_id = fields.Many2one("res.users", required=True, default=lambda self: self.env.user, readonly=True)
    processed_product_count = fields.Integer(readonly=True)
    total_product_count = fields.Integer(readonly=True)
    next_chunk_offset = fields.Integer(readonly=True, default=0)
    chunk_size = fields.Integer(default=500, required=True)

    @api.constrains("date_start", "date_end", "history_date_start", "history_date_end", "forecast_horizon", "chunk_size")
    def _check_dates(self):
        for run in self:
            if run.date_end < run.date_start or run.history_date_end < run.history_date_start:
                raise ValidationError(_("End dates must not precede start dates."))
            if run.forecast_horizon < 1 or run.chunk_size < 1:
                raise ValidationError(_("Forecast horizon and chunk size must be positive."))

    @api.onchange("sop_plan_id")
    def _onchange_plan(self):
        if self.sop_plan_id:
            self.company_id = self.sop_plan_id.company_id
            self.warehouse_ids = self.sop_plan_id.warehouse_ids
            self.date_start = self.sop_plan_id.date_start
            self.date_end = self.sop_plan_id.date_end
            self.granularity = self.sop_plan_id.planning_granularity
            self.version_id = self.sop_plan_id.active_version_id

    def action_prepare_data(self):
        for run in self:
            if run.state == "running":
                raise UserError(_("A running forecast cannot be prepared again."))
            if not run.model_ids:
                run.model_ids = self.env["mogen.sop.forecast.model"].search([("company_id", "=", run.company_id.id), ("active", "=", True)])
            if not run.model_ids:
                raise UserError(_("Select at least one active forecast model."))
            run.write({"state": "queued", "error_message": False, "calculation_log": _("Queued for deterministic batch processing."), "data_snapshot_date": fields.Datetime.now(), "processed_product_count": 0, "total_product_count": 0, "next_chunk_offset": 0})

    def _history_domain(self):
        self.ensure_one()
        domain = [("order_id.company_id", "=", self.company_id.id), ("order_id.state", "in", ["sale", "done"]), ("order_id.date_order", ">=", fields.Datetime.to_string(fields.Datetime.from_string(str(self.history_date_start)))), ("order_id.date_order", "<", fields.Datetime.to_string(fields.Datetime.from_string(str(self.history_date_end + timedelta(days=1)))))]
        if self.warehouse_ids:
            domain.append(("order_id.warehouse_id", "in", self.warehouse_ids.ids))
        return domain

    def _aggregate_history(self):
        self.ensure_one()
        period_group = "order_id.date_order:week" if self.granularity == "week" else "order_id.date_order:month"
        groups = self.env["sale.order.line"].with_context(tz=self.timezone).read_group(self._history_domain(), ["product_uom_qty:sum"], ["product_id", "product_uom", "order_id.warehouse_id", period_group], lazy=False)
        history = {}
        for group in groups:
            product = group.get("product_id")
            warehouse = group.get("order_id.warehouse_id")
            uom = group.get("product_uom")
            period_range = group.get("__range", {}).get(period_group, {})
            period_start = period_range.get("from", "")[:10]
            if not product or not warehouse or not period_start:
                continue
            product_record = self.env["product.product"].browse(product[0])
            quantity = group.get("product_uom_qty", 0.0)
            if uom and product_record.uom_id.id != uom[0]:
                quantity = self.env["uom.uom"].browse(uom[0])._compute_quantity(quantity, product_record.uom_id)
            history.setdefault((product[0], warehouse[0]), {})[period_start] = quantity
        return history

    def _future_periods(self):
        self.ensure_one()
        periods, cursor = [], self.date_start
        for _index in range(self.forecast_horizon):
            periods.append(cursor)
            cursor += timedelta(days=7 if self.granularity == "week" else 31)
        return periods

    def action_run_models(self):
        for run in self:
            if run.state == "draft":
                run.action_prepare_data()
            if run.state not in ("queued", "running", "failed"):
                raise UserError(_("Only queued, failed, or running forecasts can be processed."))
            try:
                run.write({"state": "running", "started_at": run.started_at or fields.Datetime.now(), "error_message": False})
                history = run._aggregate_history()
                keys = sorted(history)
                run.total_product_count = len(keys)
                start, stop = run.next_chunk_offset, run.next_chunk_offset + run.chunk_size
                for product_id, warehouse_id in keys[start:stop]:
                    ordered = [history[(product_id, warehouse_id)][period] for period in sorted(history[(product_id, warehouse_id)])]
                    for model in run.model_ids:
                        forecast, fallback_reason = model.calculate(ordered)
                        deviation = ForecastMath.standard_deviation(ordered) if forecast is not None else None
                        for period in run._future_periods():
                            existing = self.env["mogen.sop.forecast.result"].search_count([("forecast_run_id", "=", run.id), ("product_id", "=", product_id), ("warehouse_id", "=", warehouse_id), ("period_date", "=", period), ("model_id", "=", model.id)])
                            if existing:
                                continue
                            self.env["mogen.sop.forecast.result"].create({"forecast_run_id": run.id, "sop_plan_id": run.sop_plan_id.id, "version_id": run.version_id.id, "company_id": run.company_id.id, "warehouse_id": warehouse_id, "product_id": product_id, "period_date": period, "model_id": model.id, "historical_qty": ordered[-1] if ordered else 0.0, "forecast_qty": max(0.0, forecast or 0.0), "lower_confidence_qty": max(0.0, forecast - 1.96 * deviation) if deviation is not None else False, "upper_confidence_qty": forecast + 1.96 * deviation if deviation is not None else False, "data_points_used": len(ordered), "fallback_reason": fallback_reason or False, "is_valid": forecast is not None, "parameter_snapshot": json.dumps({"history_periods": model.history_periods, "alpha": model.alpha, "seasonal_periods": model.seasonal_periods, "weight_config": model.weight_config, "algorithm_version": model.algorithm_version}, sort_keys=True)})
                processed = min(stop, len(keys))
                values = {"processed_product_count": processed, "next_chunk_offset": processed, "calculation_log": _("Processed %(processed)s of %(total)s products.") % {"processed": processed, "total": len(keys)}}
                if processed >= len(keys):
                    values.update({"state": "completed", "completed_at": fields.Datetime.now()})
                run.write(values)
            except Exception as error:
                run.write({"state": "failed", "error_message": str(error), "calculation_log": _("Processing failed; restart from saved chunk offset.")})
                raise

    def action_cancel(self):
        self.write({"state": "cancelled", "completed_at": fields.Datetime.now()})


class MogenSopForecastResult(models.Model):
    _name = "mogen.sop.forecast.result"
    _description = "S&OP Forecast Result"
    _order = "period_date, product_id, warehouse_id, model_id"
    _check_company_auto = True

    forecast_run_id = fields.Many2one("mogen.sop.forecast.run", required=True, ondelete="cascade", index=True)
    sop_plan_id = fields.Many2one("mogen.sop.plan", required=True, check_company=True, index=True)
    version_id = fields.Many2one("mogen.sop.plan.version", index=True)
    company_id = fields.Many2one("res.company", required=True, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True, index=True)
    product_id = fields.Many2one("product.product", required=True, index=True)
    uom_id = fields.Many2one(related="product_id.uom_id", store=True, readonly=True)
    period_date = fields.Date(required=True, index=True)
    model_id = fields.Many2one("mogen.sop.forecast.model", required=True, check_company=True, index=True)
    historical_qty = fields.Float()
    forecast_qty = fields.Float(required=True)
    lower_confidence_qty = fields.Float()
    upper_confidence_qty = fields.Float()
    data_points_used = fields.Integer(required=True)
    fallback_reason = fields.Char()
    is_valid = fields.Boolean(default=True, index=True)
    parameter_snapshot = fields.Text(required=True)
    source_snapshot_date = fields.Datetime(related="forecast_run_id.data_snapshot_date", store=True, readonly=True, index=True)

    _sql_constraints = [("forecast_result_unique", "unique(forecast_run_id, product_id, warehouse_id, period_date, model_id)", "A forecast result already exists for this run, product, warehouse, period, and model.")]
