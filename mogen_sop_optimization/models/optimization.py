"""Persistent inventory optimization runs, constraints, results, and segments."""

import json
from collections import defaultdict
from datetime import date, datetime, time
from math import sqrt

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError

from ..services.inventory_math import InventoryMath


SERVICE_LEVEL_Z = {
    0.90: 1.282,
    0.95: 1.645,
    0.98: 2.054,
    0.99: 2.326,
}


class MogenSopOptimizationRun(models.Model):
    _name = "mogen.sop.optimization.run"
    _description = "S&OP Optimization Run"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc, id desc"
    _check_company_auto = True

    name = fields.Char(required=True, default=lambda self: _("New"), tracking=True)
    sop_plan_id = fields.Many2one("mogen.sop.plan", check_company=True, index=True)
    version_id = fields.Many2one("mogen.sop.plan.version", index=True)
    # Phase 3 scenarios will extend this compatibility link in Step 5.
    scenario_plan_id = fields.Many2one("mogen.sop.scenario", check_company=True, index=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    warehouse_ids = fields.Many2many("stock.warehouse", check_company=True)
    date_start = fields.Date(required=True, default=lambda self: date.today().replace(year=date.today().year - 1), index=True)
    date_end = fields.Date(required=True, default=fields.Date.today, index=True)
    optimization_type = fields.Selection([
        ("inventory", "Inventory"), ("procurement", "Procurement"), ("production", "Production"),
        ("capacity", "Capacity"), ("supplier_allocation", "Supplier Allocation"), ("integrated", "Integrated"),
    ], required=True, default="inventory", index=True)
    objective = fields.Selection([
        ("minimize_stockout", "Minimize Stockout"), ("minimize_inventory", "Minimize Inventory"),
        ("minimize_cost", "Minimize Cost"), ("maximize_service_level", "Maximize Service Level"),
        ("maximize_margin", "Maximize Margin"), ("balanced", "Balanced"),
    ], required=True, default="balanced")
    constraint_ids = fields.One2many("mogen.sop.optimization.constraint", "optimization_run_id")
    result_ids = fields.One2many("mogen.sop.optimization.result", "optimization_run_id")
    state = fields.Selection([
        ("draft", "Draft"), ("queued", "Queued"), ("running", "Running"), ("completed", "Completed"),
        ("failed", "Failed"), ("cancelled", "Cancelled"),
    ], required=True, default="draft", index=True, tracking=True)
    solver_type = fields.Selection([
        ("deterministic_rules", "Deterministic Rules"), ("linear_programming", "Linear Programming"), ("custom", "Custom"),
    ], required=True, default="deterministic_rules")
    safety_stock_method = fields.Selection([
        ("fixed", "Fixed Quantity"), ("days_of_demand", "Days of Demand"), ("statistical", "Demand Variability and Service Level"),
    ], required=True, default="statistical")
    fixed_safety_stock_qty = fields.Float(default=0.0)
    coverage_days = fields.Float(default=14.0)
    target_service_level = fields.Float(default=0.95)
    default_lead_time_days = fields.Float(default=0.0)
    default_lead_time_standard_deviation = fields.Float(default=0.0)
    default_ordering_cost = fields.Monetary(currency_field="currency_id", default=0.0)
    default_holding_cost_per_unit = fields.Monetary(currency_field="currency_id", default=0.0)
    abc_a_threshold = fields.Float(default=80.0)
    abc_b_threshold = fields.Float(default=95.0)
    xyz_x_threshold = fields.Float(default=0.50)
    xyz_y_threshold = fields.Float(default=1.00)
    chunk_size = fields.Integer(default=500, required=True)
    processed_product_count = fields.Integer(readonly=True)
    total_product_count = fields.Integer(readonly=True)
    scheduled_at = fields.Datetime(index=True)
    started_at = fields.Datetime(readonly=True)
    completed_at = fields.Datetime(readonly=True)
    calculation_log = fields.Text(readonly=True)
    error_message = fields.Text(readonly=True)
    data_snapshot_date = fields.Datetime(readonly=True, index=True)
    algorithm_version = fields.Char(required=True, default="1.0")
    requested_by_id = fields.Many2one("res.users", required=True, readonly=True, default=lambda self: self.env.user)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)

    @api.constrains("date_start", "date_end", "target_service_level", "abc_a_threshold", "abc_b_threshold", "xyz_x_threshold", "xyz_y_threshold", "chunk_size")
    def _check_inputs(self):
        for run in self:
            if run.date_start > run.date_end:
                raise ValidationError(_("The end date must not precede the start date."))
            if not 0.0 < run.target_service_level < 1.0:
                raise ValidationError(_("The target service level must be between zero and one."))
            if not 0.0 < run.abc_a_threshold < run.abc_b_threshold <= 100.0:
                raise ValidationError(_("ABC thresholds must be increasing percentages."))
            if not 0.0 <= run.xyz_x_threshold < run.xyz_y_threshold:
                raise ValidationError(_("XYZ thresholds must be increasing non-negative values."))
            if run.chunk_size < 1:
                raise ValidationError(_("Batch size must be positive."))

    def action_queue(self):
        invalid = self.filtered(lambda run: run.state not in ("draft", "failed"))
        if invalid:
            raise UserError(_("Only draft or failed optimization runs can be queued."))
        self.write({"state": "queued", "error_message": False})
        return True

    def _service_level_z(self, service_level):
        return SERVICE_LEVEL_Z[min(SERVICE_LEVEL_Z, key=lambda value: abs(value - service_level))]

    def _constraint_map(self):
        self.ensure_one()
        mapped = {}
        for constraint in self.constraint_ids:
            key = (constraint.product_id.id or False, constraint.warehouse_id.id or False, constraint.constraint_type)
            mapped[key] = constraint
        return mapped

    def _constraint_value(self, constraints, product_id, warehouse_id, constraint_type, default):
        for key in ((product_id, warehouse_id, constraint_type), (product_id, False, constraint_type), (False, warehouse_id, constraint_type), (False, False, constraint_type)):
            if key in constraints:
                constraint = constraints[key]
                return constraint.percentage_value if constraint_type == "minimum_service_level" else constraint.numeric_value
        return default

    def _demand_metrics(self):
        """Return all product/warehouse demand metrics using one grouped query."""
        self.ensure_one()
        domain = [
            ("order_id.company_id", "=", self.company_id.id),
            ("order_id.state", "in", ("sale", "done")),
            ("display_type", "=", False),
            ("order_id.date_order", ">=", fields.Datetime.to_string(datetime.combine(self.date_start, time.min))),
            ("order_id.date_order", "<=", fields.Datetime.to_string(datetime.combine(self.date_end, time.max))),
        ]
        if self.warehouse_ids:
            domain.append(("order_id.warehouse_id", "in", self.warehouse_ids.ids))
        groups = self.env["sale.order.line"].read_group(
            domain,
            ["product_uom_qty:sum", "price_subtotal:sum"],
            ["product_id", "product_uom", "order_id.warehouse_id", "order_id.date_order:month"],
            lazy=False,
        )
        metrics = defaultdict(lambda: {"period_qty": defaultdict(float), "revenue": 0.0})
        products = self.env["product.product"].browse([group["product_id"][0] for group in groups if group.get("product_id")]).exists()
        product_map = {product.id: product for product in products}
        uom_ids = [group["product_uom"][0] for group in groups if group.get("product_uom")]
        uoms = {uom.id: uom for uom in self.env["uom.uom"].browse(uom_ids).exists()}
        for group in groups:
            product = group.get("product_id")
            warehouse = group.get("order_id.warehouse_id")
            period = group.get("order_id.date_order:month")
            if not product or not warehouse or not period or product[0] not in product_map:
                continue
            quantity = group.get("product_uom_qty", 0.0)
            source_uom = uoms.get(group.get("product_uom") and group["product_uom"][0])
            if source_uom:
                quantity = source_uom._compute_quantity(quantity, product_map[product[0]].uom_id)
            values = metrics[(product[0], warehouse[0])]
            values["period_qty"][period[:7]] += quantity
            values["revenue"] += group.get("price_subtotal", 0.0)
        return metrics, product_map

    def _existing_policies(self, product_ids, warehouse_ids):
        points = self.env["stock.warehouse.orderpoint"].search([
            ("company_id", "=", self.company_id.id), ("product_id", "in", product_ids), ("warehouse_id", "in", warehouse_ids),
        ])
        values = {}
        for point in points:
            values.setdefault((point.product_id.id, point.warehouse_id.id), point)
        return values

    def _period_count(self):
        start = self.date_start.replace(day=1)
        end = self.date_end.replace(day=1)
        return max((end.year - start.year) * 12 + end.month - start.month + 1, 1)

    def action_run(self):
        for run in self:
            if run.state not in ("queued", "running"):
                raise UserError(_("Only queued optimization runs may be calculated."))
            try:
                run.write({"state": "running", "started_at": fields.Datetime.now(), "error_message": False, "data_snapshot_date": fields.Datetime.now()})
                run.result_ids.unlink()
                metrics, product_map = run._demand_metrics()
                policies = run._existing_policies(list(product_map), list({warehouse_id for _, warehouse_id in metrics}))
                constraints = run._constraint_map()
                period_count = run._period_count()
                rows = []
                for (product_id, warehouse_id), metric in metrics.items():
                    quantities = list(metric["period_qty"].values()) + [0.0] * max(period_count - len(metric["period_qty"]), 0)
                    total_qty = sum(quantities)
                    average_period = total_qty / period_count
                    deviation = sqrt(sum((qty - average_period) ** 2 for qty in quantities) / period_count) if quantities else 0.0
                    average_daily = total_qty / max((run.date_end - run.date_start).days + 1, 1)
                    annual_demand = average_daily * 365.0
                    product = product_map[product_id]
                    annual_value = annual_demand * max(product.standard_price, 0.0)
                    rows.append({"product": product, "warehouse_id": warehouse_id, "average_daily": average_daily, "annual_demand": annual_demand, "deviation": deviation / 30.0, "annual_value": annual_value})
                abc = InventoryMath.abc_classes([((row["product"].id, row["warehouse_id"]), row["annual_value"]) for row in rows], run.abc_a_threshold, run.abc_b_threshold)
                run._store_inventory_results(rows, abc, policies, constraints)
                run.write({"state": "completed", "completed_at": fields.Datetime.now(), "processed_product_count": len(rows), "total_product_count": len(rows), "calculation_log": _("Demand grouped by product, warehouse, UoM, and month. Policy changes are proposals only.")})
            except Exception as error:
                run.write({"state": "failed", "error_message": str(error), "completed_at": fields.Datetime.now()})
                raise
        return True

    def _store_inventory_results(self, rows, abc, policies, constraints):
        self.ensure_one()
        Segment = self.env["mogen.sop.inventory.segment"]
        Result = self.env["mogen.sop.optimization.result"]
        segment_values, result_values = [], []
        for row in rows:
            product, warehouse_id = row["product"], row["warehouse_id"]
            service_level = self._constraint_value(constraints, product.id, warehouse_id, "minimum_service_level", self.target_service_level)
            lead_time = self._constraint_value(constraints, product.id, warehouse_id, "lead_time", self.default_lead_time_days)
            safety_method = self.safety_stock_method
            if safety_method == "fixed":
                safety_stock = InventoryMath.fixed_safety_stock(self.fixed_safety_stock_qty)
            elif safety_method == "days_of_demand":
                safety_stock = InventoryMath.days_of_demand_safety_stock(row["average_daily"], self.coverage_days)
            else:
                safety_stock = InventoryMath.statistical_safety_stock(row["average_daily"], row["deviation"], self._service_level_z(service_level), lead_time, self.default_lead_time_standard_deviation)
            reorder = InventoryMath.reorder_point(row["average_daily"], lead_time, safety_stock)
            ordering_cost = self._constraint_value(constraints, product.id, warehouse_id, "minimum_order_quantity", self.default_ordering_cost)
            eoq = InventoryMath.eoq(row["annual_demand"], ordering_cost, self.default_holding_cost_per_unit)
            point = policies.get((product.id, warehouse_id))
            coefficient = row["deviation"] / row["average_daily"] if row["average_daily"] else 0.0
            policy_snapshot = {"old_reorder_point": point.product_min_qty if point else 0.0, "old_maximum_qty": point.product_max_qty if point else 0.0, "proposed_safety_stock": safety_stock, "proposed_reorder_point": reorder, "proposed_eoq": eoq, "formula_version": self.algorithm_version}
            segment_values.append({"company_id": self.company_id.id, "warehouse_id": warehouse_id, "product_id": product.id, "abc_class": abc[(product.id, warehouse_id)], "xyz_class": InventoryMath.xyz_class(row["average_daily"], row["deviation"], self.xyz_x_threshold, self.xyz_y_threshold), "annual_consumption_value": row["annual_value"], "demand_variability": row["deviation"], "coefficient_of_variation": coefficient, "service_level_target": service_level, "safety_stock_method": safety_method, "proposed_safety_stock_qty": safety_stock, "proposed_reorder_point_qty": reorder, "proposed_eoq_qty": eoq, "last_calculated_date": fields.Date.today(), "last_optimization_run_id": self.id, "parameter_snapshot": json.dumps(policy_snapshot, sort_keys=True)})
            result_values.append({"optimization_run_id": self.id, "company_id": self.company_id.id, "warehouse_id": warehouse_id, "product_id": product.id, "current_value": point.product_min_qty if point else 0.0, "optimized_value": reorder, "improvement_value": reorder - (point.product_min_qty if point else 0.0), "improvement_percent": 0.0, "recommended_action": "propose_inventory_policy", "expected_cost_impact": 0.0, "expected_service_impact": service_level, "expected_inventory_impact": reorder - (point.product_min_qty if point else 0.0), "feasibility_status": "feasible", "reason": _("Proposed %(method)s safety stock, reorder point, and EOQ. Approval is required before any policy can be applied.", method=dict(self._fields["safety_stock_method"].selection).get(safety_method)), "policy_state": "proposed", "old_policy_values": json.dumps({"reorder_point": point.product_min_qty if point else 0.0, "maximum_qty": point.product_max_qty if point else 0.0}, sort_keys=True), "proposed_policy_values": json.dumps(policy_snapshot, sort_keys=True), "algorithm_version": self.algorithm_version})
        Segment.search([("company_id", "=", self.company_id.id), ("warehouse_id", "in", [row["warehouse_id"] for row in rows]), ("product_id", "in", [row["product"].id for row in rows])]).unlink()
        for index in range(0, len(segment_values), self.chunk_size):
            Segment.create(segment_values[index:index + self.chunk_size])
            Result.create(result_values[index:index + self.chunk_size])

    @api.model
    def cron_recalculate_planned_runs(self):
        runs = self.search([("state", "=", "queued"), ("scheduled_at", "!=", False), ("scheduled_at", "<=", fields.Datetime.now())], order="scheduled_at, id", limit=20)
        for run in runs:
            try:
                run.sudo().action_run()
            except Exception:
                self.env.cr.rollback()
        return True


class MogenSopOptimizationConstraint(models.Model):
    _name = "mogen.sop.optimization.constraint"
    _description = "S&OP Optimization Constraint"
    _check_company_auto = True

    optimization_run_id = fields.Many2one("mogen.sop.optimization.run", required=True, ondelete="cascade", check_company=True, index=True)
    company_id = fields.Many2one(related="optimization_run_id.company_id", store=True, readonly=True, index=True)
    constraint_type = fields.Selection([
        ("minimum_service_level", "Minimum Service Level"), ("maximum_inventory_value", "Maximum Inventory Value"), ("maximum_cash_requirement", "Maximum Cash Requirement"), ("supplier_capacity", "Supplier Capacity"), ("workcenter_capacity", "Work Center Capacity"), ("warehouse_capacity", "Warehouse Capacity"), ("minimum_order_quantity", "Ordering Cost"), ("production_batch_size", "Production Batch Size"), ("lead_time", "Lead Time"), ("minimum_safety_stock", "Minimum Safety Stock"), ("maximum_overtime", "Maximum Overtime"),
    ], required=True, index=True)
    product_id = fields.Many2one("product.product", index=True)
    warehouse_id = fields.Many2one("stock.warehouse", check_company=True, index=True)
    supplier_id = fields.Many2one("res.partner", check_company=True, index=True)
    workcenter_id = fields.Many2one("mrp.workcenter", check_company=True, index=True)
    numeric_value = fields.Float(default=0.0)
    percentage_value = fields.Float(default=0.0)
    hard_constraint = fields.Boolean(default=True)
    penalty_weight = fields.Float(default=1.0)
    note = fields.Text()

    @api.constrains("numeric_value", "percentage_value", "penalty_weight")
    def _check_values(self):
        for constraint in self:
            if constraint.numeric_value < 0 or constraint.percentage_value < 0 or constraint.penalty_weight < 0:
                raise ValidationError(_("Constraint values cannot be negative."))
            if constraint.constraint_type == "minimum_service_level" and not 0.0 < constraint.percentage_value < 1.0:
                raise ValidationError(_("A service-level constraint must be between zero and one."))


class MogenSopOptimizationResult(models.Model):
    _name = "mogen.sop.optimization.result"
    _description = "S&OP Optimization Result"
    _order = "optimization_run_id desc, warehouse_id, product_id"
    _check_company_auto = True

    optimization_run_id = fields.Many2one("mogen.sop.optimization.run", required=True, ondelete="cascade", check_company=True, index=True)
    company_id = fields.Many2one(related="optimization_run_id.company_id", store=True, readonly=True, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True, index=True)
    product_id = fields.Many2one("product.product", required=True, index=True)
    supplier_id = fields.Many2one("res.partner", check_company=True, index=True)
    workcenter_id = fields.Many2one("mrp.workcenter", check_company=True, index=True)
    period_date = fields.Date(index=True)
    current_value = fields.Float()
    optimized_value = fields.Float()
    improvement_value = fields.Float()
    improvement_percent = fields.Float()
    recommended_action = fields.Selection([("propose_inventory_policy", "Propose Inventory Policy")], required=True)
    expected_cost_impact = fields.Monetary(currency_field="currency_id")
    expected_service_impact = fields.Float()
    expected_inventory_impact = fields.Float()
    feasibility_status = fields.Selection([("feasible", "Feasible"), ("infeasible", "Infeasible"), ("warning", "Warning")], required=True, default="feasible")
    reason = fields.Text(required=True)
    policy_state = fields.Selection([("proposed", "Proposed"), ("approved", "Approved"), ("rejected", "Rejected")], required=True, default="proposed", index=True)
    old_policy_values = fields.Text(required=True, readonly=True)
    proposed_policy_values = fields.Text(required=True, readonly=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, check_company=True)
    approved_at = fields.Datetime(readonly=True)
    algorithm_version = fields.Char(required=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)

    def action_approve_policy(self):
        if not self.env.user.has_group("mogen_sop_core.group_sop_manager"):
            raise AccessError(_("Only an S&OP manager can approve a proposed inventory policy."))
        if any(result.policy_state != "proposed" for result in self):
            raise UserError(_("Only proposed policy recommendations can be approved."))
        self.write({"policy_state": "approved", "approved_by_id": self.env.user.id, "approved_at": fields.Datetime.now()})
        return True

    def action_reject_policy(self):
        if not self.env.user.has_group("mogen_sop_core.group_sop_manager"):
            raise AccessError(_("Only an S&OP manager can reject a proposed inventory policy."))
        self.filtered(lambda result: result.policy_state == "proposed").write({"policy_state": "rejected"})
        return True


class MogenSopInventorySegment(models.Model):
    _name = "mogen.sop.inventory.segment"
    _description = "S&OP Inventory Segment"
    _order = "company_id, warehouse_id, abc_class, product_id"
    _check_company_auto = True

    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True, index=True)
    product_id = fields.Many2one("product.product", required=True, index=True)
    abc_class = fields.Selection([("A", "A"), ("B", "B"), ("C", "C")], required=True, index=True)
    xyz_class = fields.Selection([("X", "X"), ("Y", "Y"), ("Z", "Z")], required=True, index=True)
    annual_consumption_value = fields.Monetary(currency_field="currency_id")
    demand_variability = fields.Float()
    coefficient_of_variation = fields.Float()
    service_level_target = fields.Float()
    safety_stock_method = fields.Selection([("fixed", "Fixed Quantity"), ("days_of_demand", "Days of Demand"), ("statistical", "Statistical")], required=True)
    proposed_safety_stock_qty = fields.Float(readonly=True)
    proposed_reorder_point_qty = fields.Float(readonly=True)
    proposed_eoq_qty = fields.Float(readonly=True)
    last_calculated_date = fields.Date(index=True)
    last_optimization_run_id = fields.Many2one("mogen.sop.optimization.run", readonly=True, ondelete="set null", index=True)
    parameter_snapshot = fields.Text(readonly=True)
    currency_id = fields.Many2one(related="company_id.currency_id", store=True, readonly=True)

    _sql_constraints = [("inventory_segment_unique", "unique(company_id, warehouse_id, product_id)", "Only one current inventory segment is allowed per company, warehouse, and product.")]
