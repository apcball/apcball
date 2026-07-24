from collections import defaultdict
from datetime import datetime, time, timedelta
from math import ceil

from pytz import UTC, timezone

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_round


class MogenSopProductionPlan(models.Model):
    _name = "mogen.sop.production.plan"
    _description = "S&OP Production Plan"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, code desc"
    _check_company_auto = True

    name = fields.Char(required=True, default="New", tracking=True)
    code = fields.Char(required=True, copy=False, readonly=True, index=True)
    sop_plan_id = fields.Many2one(
        "mogen.sop.plan",
        required=True,
        ondelete="restrict",
        check_company=True,
        index=True,
        tracking=True,
    )
    version_id = fields.Many2one(
        "mogen.sop.plan.version",
        index=True,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        check_company=True,
        index=True,
        tracking=True,
    )
    date_start = fields.Date(required=True, index=True)
    date_end = fields.Date(required=True, index=True)
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("calculated", "Calculated"),
            ("review", "In Review"),
            ("approved", "Approved"),
            ("executed", "Executed"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        readonly=True,
        tracking=True,
        index=True,
    )
    line_ids = fields.One2many("mogen.sop.production.line", "production_plan_id")
    material_line_ids = fields.One2many(
        "mogen.sop.material.requirement", "production_plan_id", readonly=True
    )
    capacity_line_ids = fields.One2many(
        "mogen.sop.workcenter.capacity", "production_plan_id", readonly=True
    )
    capacity_line_count = fields.Integer(compute="_compute_capacity_line_count")
    overload_alert_count = fields.Integer(compute="_compute_capacity_line_count")
    total_required_qty = fields.Float(compute="_compute_totals", store=True)
    total_planned_qty = fields.Float(compute="_compute_totals", store=True)
    total_completed_qty = fields.Float(compute="_compute_totals", store=True)
    total_shortage_qty = fields.Float(compute="_compute_totals", store=True)
    average_capacity_load = fields.Float(
        readonly=True,
        help="Reserved for the capacity-planning phase.",
    )
    capacity_warning_threshold = fields.Float(required=True, default=85.0)
    capacity_overload_threshold = fields.Float(required=True, default=100.0)
    note = fields.Text()
    user_id = fields.Many2one(
        "res.users",
        default=lambda self: self.env.user,
        required=True,
        check_company=True,
    )
    manager_id = fields.Many2one("res.users", check_company=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, check_company=True)
    approved_date = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("mogen_sop_production_plan_code_uniq", "unique(code)", "Production plan code must be unique."),
    ]

    @api.depends(
        "line_ids.required_production_qty",
        "line_ids.planned_production_qty",
        "line_ids.completed_qty",
    )
    def _compute_totals(self):
        for plan in self:
            plan.total_required_qty = sum(plan.line_ids.mapped("required_production_qty"))
            plan.total_planned_qty = sum(plan.line_ids.mapped("planned_production_qty"))
            plan.total_completed_qty = sum(plan.line_ids.mapped("completed_qty"))
            plan.total_shortage_qty = sum(
                max(0.0, line.required_production_qty - line.planned_production_qty)
                for line in plan.line_ids
            )

    @api.depends("capacity_line_ids")
    def _compute_capacity_line_count(self):
        for plan in self:
            plan.capacity_line_count = len(plan.capacity_line_ids)
            plan.overload_alert_count = len(
                plan.capacity_line_ids.mapped("alert_id").filtered(
                    lambda alert: alert.state != "resolved"
                )
            )

    @api.constrains("date_start", "date_end")
    def _check_date_range(self):
        if any(plan.date_start > plan.date_end for plan in self):
            raise ValidationError(_("The production plan end date must not precede its start date."))

    @api.constrains("capacity_warning_threshold", "capacity_overload_threshold")
    def _check_capacity_thresholds(self):
        for plan in self:
            if (
                plan.capacity_warning_threshold < 0.0
                or plan.capacity_overload_threshold < plan.capacity_warning_threshold
            ):
                raise ValidationError(
                    _("Capacity thresholds must be non-negative and overload must not precede warning.")
                )

    @api.constrains("sop_plan_id", "version_id", "warehouse_id", "company_id")
    def _check_plan_relations(self):
        for plan in self:
            if plan.sop_plan_id.company_id != plan.company_id:
                raise ValidationError(_("The S&OP plan and production plan must belong to the same company."))
            if plan.version_id and plan.version_id.plan_id != plan.sop_plan_id:
                raise ValidationError(_("The selected version must belong to the selected S&OP plan."))
            if plan.warehouse_id.company_id != plan.company_id:
                raise ValidationError(_("The warehouse must belong to the production-plan company."))
            if plan.sop_plan_id.warehouse_ids and plan.warehouse_id not in plan.sop_plan_id.warehouse_ids:
                raise ValidationError(_("The warehouse must be included in the S&OP plan."))

    @api.model_create_multi
    def create(self, vals_list):
        for values in vals_list:
            if values.get("state", "draft") != "draft":
                raise UserError(_("New production plans must start in Draft."))
            if values.get("code", "New") in (False, "New"):
                values["code"] = self.env["ir.sequence"].next_by_code("mogen.sop.production.plan") or "New"
            if values.get("name", "New") == "New":
                values["name"] = values["code"]
            if not values.get("version_id") and values.get("sop_plan_id"):
                values["version_id"] = self.env["mogen.sop.plan"].browse(
                    values["sop_plan_id"]
                ).active_version_id.id
        return super().create(vals_list)

    def write(self, values):
        if "state" in values:
            raise UserError(_("Use production planning workflow actions to change state."))
        if any(plan.state != "draft" for plan in self):
            raise AccessError(_("Only draft production plans can be changed."))
        return super().write(values)

    def _write_workflow_values(self, values):
        return super(MogenSopProductionPlan, self).write(values)

    def _require_manager(self):
        if not self.env.user.has_group("mogen_sop_core.group_sop_manager"):
            raise AccessError(_("Only an S&OP manager can approve or execute a production plan."))

    def _transition(self, allowed_states, target_state, values=None):
        if any(plan.state not in allowed_states for plan in self):
            raise UserError(_("This workflow transition is not available from the current state."))
        values = dict(values or {}, state=target_state)
        return self._write_workflow_values(values)

    @api.model
    def _required_production_qty(self, demand_qty, safety_stock_qty, free_stock_qty, incoming_mo_qty):
        return max(0.0, demand_qty + safety_stock_qty - free_stock_qty - incoming_mo_qty)

    @api.model
    def _round_production_qty(self, quantity, policy_batch_size, bom_batch_size, uom_rounding):
        batch_size = policy_batch_size or bom_batch_size or uom_rounding
        if not batch_size:
            return quantity
        return float_round(quantity, precision_rounding=batch_size, rounding_method="UP")

    @api.model
    def _warehouse_for_location(self, location, warehouses):
        parent_path = location.parent_path or ""
        for warehouse in warehouses:
            if parent_path.startswith("%s/" % warehouse.lot_stock_id.id):
                return warehouse.id
        return False

    def _get_stock_metrics(self, products):
        self.ensure_one()
        warehouse = self.warehouse_id
        product_ids = products.ids
        if not product_ids:
            return {}, {}, {}

        quant_groups = self.env["stock.quant"].read_group(
            [
                ("company_id", "=", self.company_id.id),
                ("product_id", "in", product_ids),
                ("location_id", "child_of", warehouse.lot_stock_id.id),
            ],
            ["product_id", "quantity:sum", "reserved_quantity:sum"],
            ["product_id"],
            lazy=False,
        )
        free_qty_by_product = {
            group["product_id"][0]: group.get("quantity", 0.0) - group.get("reserved_quantity", 0.0)
            for group in quant_groups
            if group.get("product_id")
        }

        orderpoints = self.env["stock.warehouse.orderpoint"].search(
            [
                ("company_id", "=", self.company_id.id),
                ("warehouse_id", "=", warehouse.id),
                ("product_id", "in", product_ids),
                ("active", "=", True),
            ]
        )
        safety_qty_by_product = defaultdict(float)
        batch_size_by_product = defaultdict(float)
        for orderpoint in orderpoints:
            safety_qty_by_product[orderpoint.product_id.id] += orderpoint.product_min_qty
            batch_size_by_product[orderpoint.product_id.id] = max(
                batch_size_by_product[orderpoint.product_id.id], orderpoint.qty_multiple
            )

        incoming_groups = self.env["mrp.production"].read_group(
            [
                ("company_id", "=", self.company_id.id),
                ("product_id", "in", product_ids),
                ("state", "not in", ("done", "cancel")),
                ("location_dest_id", "child_of", warehouse.lot_stock_id.id),
            ],
            ["product_id", "product_qty:sum"],
            ["product_id"],
            lazy=False,
        )
        incoming_qty_by_product = {
            group["product_id"][0]: group.get("product_qty", 0.0)
            for group in incoming_groups
            if group.get("product_id")
        }
        return free_qty_by_product, safety_qty_by_product, {
            product_id: (incoming_qty_by_product.get(product_id, 0.0), batch_size_by_product.get(product_id, 0.0))
            for product_id in product_ids
        }

    def _get_boms_by_product(self, products):
        self.ensure_one()
        if not products:
            return {}
        boms = self.env["mrp.bom"].search(
            [
                ("company_id", "in", (False, self.company_id.id)),
                ("type", "=", "normal"),
                "|",
                ("product_id", "in", products.ids),
                "&",
                ("product_id", "=", False),
                ("product_tmpl_id", "in", products.mapped("product_tmpl_id").ids),
            ],
            order="sequence, id",
        )
        exact_boms = {}
        template_boms = {}
        for bom in boms:
            if bom.product_id and bom.product_id.id not in exact_boms:
                exact_boms[bom.product_id.id] = bom
            elif not bom.product_id and bom.product_tmpl_id.id not in template_boms:
                template_boms[bom.product_tmpl_id.id] = bom
        return {
            product.id: exact_boms.get(product.id) or template_boms.get(product.product_tmpl_id.id)
            for product in products
        }

    def _get_normal_boms_by_product(self, products):
        """Return the standard Odoo-selected normal BOM for each product."""
        self.ensure_one()
        if not products:
            return {}
        bom_by_product = self.env["mrp.bom"].sudo()._bom_find(
            products,
            company_id=self.company_id.id,
            bom_type="normal",
        )
        return {
            product.id: bom_by_product.get(product, self.env["mrp.bom"])
            for product in products
        }

    def action_calculate_production(self):
        for plan in self:
            if plan.state not in ("draft", "calculated"):
                raise UserError(_("Only draft or calculated production plans can be recalculated."))
            recommendations = self.env["mogen.sop.recommendation"].sudo().search(
                [
                    ("plan_id", "=", plan.sop_plan_id.id),
                    ("company_id", "=", plan.company_id.id),
                    ("warehouse_id", "=", plan.warehouse_id.id),
                    ("recommendation_type", "=", "manufacture"),
                    ("state", "=", "approved"),
                    ("required_date", ">=", plan.date_start),
                    ("required_date", "<=", plan.date_end),
                ],
                order="required_date, product_id, id",
            )
            products = recommendations.mapped("product_id")
            free_qty, safety_qty, incoming_and_batch = plan._get_stock_metrics(products)
            boms_by_product = plan._get_boms_by_product(products)

            grouped_recommendations = defaultdict(lambda: self.env["mogen.sop.recommendation"])
            for recommendation in recommendations:
                grouped_recommendations[(recommendation.product_id.id, recommendation.required_date)] |= recommendation

            line_values = []
            products_by_id = {product.id: product for product in products}
            allocation_by_product = defaultdict(
                lambda: {"free": 0.0, "incoming": 0.0, "first_period": True}
            )
            for (product_id, period_date), source_recommendations in grouped_recommendations.items():
                product = products_by_id[product_id]
                bom = boms_by_product.get(product_id)
                demand_qty = sum(source_recommendations.mapped("quantity"))
                source_incoming_qty, policy_batch_size = incoming_and_batch.get(product_id, (0.0, 0.0))
                allocation = allocation_by_product[product_id]
                if allocation["first_period"]:
                    allocation["free"] = free_qty.get(product_id, 0.0)
                    allocation["incoming"] = source_incoming_qty
                safety_qty_for_period = safety_qty.get(product_id, 0.0) if allocation["first_period"] else 0.0
                free_qty_for_period = allocation["free"]
                incoming_qty_for_period = allocation["incoming"]
                required_qty = plan._required_production_qty(
                    demand_qty,
                    safety_qty_for_period,
                    free_qty_for_period,
                    incoming_qty_for_period,
                )
                available_after_demand = max(
                    0.0,
                    allocation["free"] + allocation["incoming"] - safety_qty_for_period - demand_qty,
                )
                allocation["free"] = min(allocation["free"], available_after_demand)
                allocation["incoming"] = max(0.0, available_after_demand - allocation["free"])
                allocation["first_period"] = False
                bom_batch_size = 0.0
                if bom and bom.product_qty:
                    bom_batch_size = bom.product_uom_id._compute_quantity(
                        bom.product_qty, product.uom_id
                    )
                planned_qty = plan._round_production_qty(
                    required_qty,
                    policy_batch_size,
                    bom_batch_size,
                    product.uom_id.rounding,
                )
                line_values.append(
                    {
                        "production_plan_id": plan.id,
                        "product_id": product_id,
                        "bom_id": bom.id if bom else False,
                        "period_date": period_date,
                        "demand_qty": demand_qty,
                        "safety_stock_qty": safety_qty_for_period,
                        "free_stock_qty": free_qty_for_period,
                        "incoming_mo_qty": incoming_qty_for_period,
                        "required_production_qty": required_qty,
                        "planned_production_qty": planned_qty,
                        "batch_size": policy_batch_size or bom_batch_size or product.uom_id.rounding,
                        "recommendation_ids": [(6, 0, source_recommendations.ids)],
                    }
                )
            plan.capacity_line_ids.sudo().unlink()
            plan.material_line_ids.sudo().unlink()
            plan.line_ids.sudo().unlink()
            self.env["mogen.sop.production.line"].sudo().create(line_values)
            plan._transition(("draft", "calculated"), "calculated")
        return True

    def _explode_material_components(self, root_lines):
        """Batch-expand normal BOM levels while retaining Odoo phantom behavior."""
        self.ensure_one()
        pending = [
            (line, line.product_id, line.planned_production_qty, line.bom_id, frozenset())
            for line in root_lines
        ]
        components = []
        while pending:
            leaves = []
            for line, product, quantity, bom, ancestry in pending:
                if bom.id in ancestry:
                    raise ValidationError(
                        _("Recursive BOM detected while expanding '%s'.") % product.display_name
                    )
                _boms, exploded_lines = bom.sudo().explode(product, quantity)
                next_ancestry = ancestry | {bom.id}
                for bom_line, values in exploded_lines:
                    component = bom_line.product_id
                    component_qty = bom_line.product_uom_id._compute_quantity(
                        values["qty"], component.uom_id, round=False
                    )
                    leaves.append((line, component, component_qty, next_ancestry))
            child_boms = self._get_normal_boms_by_product(
                self.env["product.product"].browse(
                    list({component.id for line, component, quantity, ancestry in leaves})
                )
            )
            pending = []
            for line, component, quantity, ancestry in leaves:
                child_bom = child_boms.get(component.id)
                if child_bom:
                    pending.append((line, component, quantity, child_bom, ancestry))
                else:
                    components.append((line, component, quantity))
        return components

    def _get_material_stock(self, products):
        """Return warehouse-specific on-hand and free component quantities."""
        self.ensure_one()
        if not products:
            return {}, {}
        groups = self.env["stock.quant"].sudo().read_group(
            [
                ("company_id", "=", self.company_id.id),
                ("product_id", "in", products.ids),
                ("location_id", "child_of", self.warehouse_id.lot_stock_id.id),
            ],
            ["product_id", "quantity:sum", "reserved_quantity:sum"],
            ["product_id"],
            lazy=False,
        )
        on_hand = {group["product_id"][0]: group.get("quantity", 0.0) for group in groups}
        free = {
            group["product_id"][0]: group.get("quantity", 0.0)
            - group.get("reserved_quantity", 0.0)
            for group in groups
        }
        return on_hand, free

    def _get_material_incoming_events(self, products):
        """Return dated confirmed-PO and planned-MO inbound quantities in product UoM."""
        self.ensure_one()
        events = defaultdict(list)
        if not products:
            return events
        purchase_lines = self.env["purchase.order.line"].sudo().search(
            [
                ("company_id", "=", self.company_id.id),
                ("product_id", "in", products.ids),
                ("order_id.state", "in", ("purchase", "done")),
                ("order_id.picking_type_id.warehouse_id", "=", self.warehouse_id.id),
            ]
        )
        for line in purchase_lines:
            quantity = line.product_uom._compute_quantity(
                max(0.0, line.product_qty - line.qty_received),
                line.product_id.uom_id,
                round=False,
            )
            if quantity:
                events[line.product_id.id].append(
                    (line.date_planned.date() if line.date_planned else self.date_end, quantity)
                )
        productions = self.env["mrp.production"].sudo().search(
            [
                ("company_id", "=", self.company_id.id),
                ("product_id", "in", products.ids),
                ("state", "not in", ("done", "cancel")),
                ("location_dest_id", "child_of", self.warehouse_id.lot_stock_id.id),
            ]
        )
        for production in productions:
            events[production.product_id.id].append(
                (
                    production.date_finished.date()
                    if production.date_finished
                    else self.date_end,
                    production.product_qty,
                )
            )
        for product_id in events:
            events[product_id].sort(key=lambda event: event[0])
        return events

    @api.model
    def _material_status(self, required_qty, free_qty, incoming_qty):
        available_qty = free_qty + incoming_qty
        if required_qty <= available_qty:
            return "available"
        if available_qty > 0.0:
            return "partial"
        return "shortage"

    @api.model
    def _procurement_route_for_product(self, product):
        routes = product.route_ids | product.categ_id.total_route_ids
        actions = set(routes.rule_ids.mapped("action"))
        if "manufacture" in actions:
            return "manufacture"
        if "buy" in actions:
            return "purchase"
        if "pull" in actions:
            return "transfer"
        return "purchase"

    def action_calculate_material_requirements(self):
        """Store aggregated material requirements for the calculated production plan."""
        for plan in self:
            if plan.state != "calculated":
                raise UserError(_("Material requirements can only be calculated for a calculated plan."))
            aggregated = defaultdict(lambda: {"quantity": 0.0, "line_ids": set(), "bom_ids": set()})
            root_lines = plan.line_ids.filtered(lambda item: item.bom_id and item.planned_production_qty)
            for line, component, quantity in plan._explode_material_components(root_lines):
                key = (component.id, line.period_date)
                aggregated[key]["quantity"] += quantity
                aggregated[key]["line_ids"].add(line.id)
                aggregated[key]["bom_ids"].add(line.bom_id.id)

            products = self.env["product.product"].browse(
                list({component_id for component_id, period_date in aggregated})
            )
            on_hand_by_product, free_by_product = plan._get_material_stock(products)
            incoming_events = plan._get_material_incoming_events(products)
            remaining_by_product = {
                product.id: {"free": free_by_product.get(product.id, 0.0), "incoming": 0.0}
                for product in products
            }
            event_positions = defaultdict(int)
            requirement_values = {}
            for (component_id, period_date), values in sorted(
                aggregated.items(), key=lambda item: (item[0][0], item[0][1])
            ):
                component = self.env["product.product"].browse(component_id)
                availability = remaining_by_product[component_id]
                events = incoming_events.get(component_id, [])
                while (
                    event_positions[component_id] < len(events)
                    and events[event_positions[component_id]][0] <= period_date
                ):
                    availability["incoming"] += events[event_positions[component_id]][1]
                    event_positions[component_id] += 1
                required_qty = values["quantity"]
                free_qty = availability["free"]
                incoming_qty = availability["incoming"]
                shortage_qty = max(0.0, required_qty - free_qty - incoming_qty)
                available_after = max(0.0, free_qty + incoming_qty - required_qty)
                availability["free"] = min(free_qty, available_after)
                availability["incoming"] = max(0.0, available_after - availability["free"])
                line_ids = sorted(values["line_ids"])
                bom_ids = sorted(values["bom_ids"])
                requirement_values[(component_id, period_date)] = {
                    "production_plan_id": plan.id,
                    "production_line_id": line_ids[0],
                    "production_line_ids": [(6, 0, line_ids)],
                    "company_id": plan.company_id.id,
                    "warehouse_id": plan.warehouse_id.id,
                    "parent_product_id": self.env["mogen.sop.production.line"].browse(
                        line_ids[0]
                    ).product_id.id,
                    "component_id": component_id,
                    "bom_id": bom_ids[0],
                    "bom_ids": [(6, 0, bom_ids)],
                    "required_qty": required_qty,
                    "on_hand_qty": on_hand_by_product.get(component_id, 0.0),
                    "free_qty": free_qty,
                    "incoming_qty": incoming_qty,
                    "shortage_qty": shortage_qty,
                    "required_date": period_date,
                    "status": plan._material_status(required_qty, free_qty, incoming_qty),
                    "procurement_route": plan._procurement_route_for_product(component),
                }
            existing = {
                (requirement.component_id.id, requirement.required_date): requirement
                for requirement in plan.material_line_ids
            }
            stale = plan.material_line_ids.filtered(
                lambda requirement: (requirement.component_id.id, requirement.required_date)
                not in requirement_values
            )
            non_draft_recommendations = stale.mapped("recommendation_id").filtered(
                lambda recommendation: recommendation.state != "draft"
            )
            if non_draft_recommendations:
                raise UserError(
                    _("Material requirements linked to non-draft recommendations cannot be recalculated.")
                )
            stale.mapped("recommendation_id").filtered(
                lambda recommendation: recommendation.state == "draft"
            ).sudo().unlink()
            stale.sudo().unlink()
            for key, values in requirement_values.items():
                if key in existing:
                    recommendation = existing[key].recommendation_id
                    if recommendation and recommendation.state != "draft":
                        raise UserError(
                            _("Material requirements linked to non-draft recommendations cannot be recalculated.")
                        )
                    if recommendation and not values["shortage_qty"]:
                        recommendation.sudo().unlink()
                        values["recommendation_id"] = False
                    elif recommendation:
                        recommendation.sudo().write(
                            {
                                "recommendation_type": values["procurement_route"],
                                "quantity": values["shortage_qty"],
                                "required_date": values["required_date"],
                            }
                        )
                    existing[key].sudo().write(values)
                else:
                    self.env["mogen.sop.material.requirement"].sudo().create(values)
        return True

    def action_generate_material_recommendations(self):
        """Create only draft, idempotent procurement recommendations for shortages."""
        recommendation_model = self.env["mogen.sop.recommendation"].sudo()
        for plan in self:
            if plan.state not in ("calculated", "review"):
                raise UserError(_("Material recommendations require a calculated or reviewed plan."))
            plan._require_manager()
            for requirement in plan.material_line_ids.filtered("shortage_qty"):
                if requirement.recommendation_id:
                    continue
                recommendation = recommendation_model.search(
                    [
                        ("source_model", "=", "mogen.sop.material.requirement"),
                        ("source_res_id", "=", requirement.id),
                    ],
                    limit=1,
                )
                if recommendation and recommendation.state != "draft":
                    raise UserError(
                        _("A non-draft material recommendation already exists for this requirement.")
                    )
                if not recommendation:
                    recommendation = recommendation_model.create(
                        {
                            "name": _("Material shortage: %s")
                            % requirement.component_id.sudo().display_name,
                            "plan_id": plan.sop_plan_id.id,
                            "recommendation_type": requirement.procurement_route,
                            "product_id": requirement.component_id.id,
                            "warehouse_id": plan.warehouse_id.id,
                            "quantity": requirement.shortage_qty,
                            "required_date": requirement.required_date,
                            "priority": "1",
                            "source_model": "mogen.sop.material.requirement",
                            "source_res_id": requirement.id,
                            "reason": _("Generated from S&OP material shortage."),
                            "create_uid": self.env.user.id,
                        }
                    )
                requirement.sudo().write({"recommendation_id": recommendation.id})
        return True

    @api.model
    def _capacity_status(
        self,
        capacity_load_percent,
        warning_threshold,
        overload_threshold,
        planned_hours,
        effective_available_hours,
    ):
        if not planned_hours:
            return "available"
        if not effective_available_hours:
            return "overloaded"
        if capacity_load_percent > overload_threshold:
            return "overloaded"
        if capacity_load_percent >= warning_threshold:
            return "warning"
        return "available"

    @api.model
    def _capacity_recommendation(self, status, overload_hours):
        if status == "overloaded":
            return _("Increase available capacity or move %.2f planned hours to an alternative period.") % overload_hours
        if status == "warning":
            return _("Monitor capacity closely and validate working-hour availability before release.")
        return _("Capacity is available for the planned workload.")

    def _get_calendar_capacity_hours(self, workcenters, period_dates):
        """Batch resource-calendar availability by calendar and planning period."""
        self.ensure_one()
        availability = defaultdict(float)
        working_intervals = defaultdict(list)
        period_bounds = {}
        workcenters_by_calendar = defaultdict(lambda: self.env["mrp.workcenter"])
        for workcenter in workcenters:
            workcenters_by_calendar[workcenter.resource_calendar_id] |= workcenter
        for calendar, calendar_workcenters in workcenters_by_calendar.items():
            if not calendar:
                continue
            for period_date in period_dates:
                calendar_timezone = timezone(calendar.tz or "UTC")
                start = calendar_timezone.localize(datetime.combine(period_date, time.min)).astimezone(UTC)
                end = calendar_timezone.localize(
                    datetime.combine(period_date + timedelta(days=1), time.min)
                ).astimezone(UTC)
                intervals_by_resource = calendar._work_intervals_batch(
                    start,
                    end,
                    resources=calendar_workcenters.resource_id,
                    compute_leaves=True,
                )
                for workcenter in calendar_workcenters:
                    intervals = [
                        (interval_start.astimezone(UTC), stop.astimezone(UTC))
                        for interval_start, stop, metadata in intervals_by_resource.get(
                            workcenter.resource_id.id, []
                        )
                    ]
                    work_hours = sum(
                        (stop - interval_start).total_seconds() / 3600.0
                        for interval_start, stop in intervals
                    )
                    working_intervals[(workcenter.id, period_date)] = intervals
                    period_bounds[(workcenter.id, period_date)] = (start, end)
                    availability[(workcenter.id, period_date)] = (
                        work_hours * workcenter.default_capacity
                    )
        return availability, working_intervals, period_bounds

    def _get_maintenance_hours(self, workcenters, working_intervals, period_bounds):
        """Return planned maintenance hours intersected with working intervals."""
        self.ensure_one()
        maintenance = defaultdict(float)
        if not workcenters or not period_bounds:
            return maintenance
        start = min(bounds[0] for bounds in period_bounds.values())
        end = max(bounds[1] for bounds in period_bounds.values())
        downtimes = self.env["mrp.workcenter.productivity"].sudo().search(
            [
                ("company_id", "=", self.company_id.id),
                ("workcenter_id", "in", workcenters.ids),
                ("loss_type", "=", "availability"),
                ("loss_id.is_sop_maintenance", "=", True),
                ("date_start", "<", fields.Datetime.to_string(end)),
                "|",
                ("date_end", "=", False),
                ("date_end", ">", fields.Datetime.to_string(start)),
            ]
        )
        for downtime in downtimes:
            downtime_start = fields.Datetime.to_datetime(downtime.date_start).replace(tzinfo=UTC)
            downtime_end = (
                fields.Datetime.to_datetime(downtime.date_end).replace(tzinfo=UTC)
                if downtime.date_end
                else end
            )
            for key, intervals in working_intervals.items():
                if key[0] != downtime.workcenter_id.id:
                    continue
                for interval_start, interval_end in intervals:
                    overlap_start = max(downtime_start, interval_start)
                    overlap_end = min(downtime_end, interval_end)
                    if overlap_end > overlap_start:
                        maintenance[key] += (
                            (overlap_end - overlap_start).total_seconds() / 3600.0
                            * downtime.workcenter_id.default_capacity
                        )
        return maintenance

    def _sync_capacity_alert(self, capacity):
        """Maintain one open capacity alert per stored capacity row."""
        alert = capacity.alert_id
        if capacity.status != "overloaded":
            if alert and alert.state != "resolved":
                alert.sudo().action_resolve()
            return
        message = _("%s is overloaded by %.2f hours on %s.") % (
            capacity.workcenter_id.display_name,
            capacity.overload_hours,
            fields.Date.to_string(capacity.period_date),
        )
        if alert:
            alert.sudo().write({"message": message, "severity": "critical"})
            return
        alert = self.env["mogen.sop.alert"].sudo().create(
            {
                "name": _("Workcenter capacity overload"),
                "plan_id": capacity.production_plan_id.sop_plan_id.id,
                "alert_type": "capacity",
                "severity": "critical",
                "warehouse_id": capacity.production_plan_id.warehouse_id.id,
                "message": message,
                "assigned_user_id": capacity.production_plan_id.manager_id.id,
                "create_uid": self.env.user.id,
            }
        )
        capacity.sudo().write({"alert_id": alert.id})

    def action_calculate_capacity(self):
        """Calculate and store workcenter load without sequencing any production."""
        for plan in self:
            if plan.state != "calculated":
                raise UserError(_("Capacity can only be calculated for a calculated plan."))
            production_lines = plan.line_ids.filtered(
                lambda line: line.bom_id and line.planned_production_qty
            )
            boms = production_lines.mapped("bom_id")
            operations_by_bom = defaultdict(lambda: self.env["mrp.routing.workcenter"])
            for operation in self.env["mrp.routing.workcenter"].sudo().search(
                [("bom_id", "in", boms.ids), ("active", "=", True)]
            ):
                operations_by_bom[operation.bom_id.id] |= operation
            planned_by_key = defaultdict(float)
            for line in production_lines:
                for operation in operations_by_bom[line.bom_id.id]:
                    if operation._skip_operation_line(line.product_id):
                        continue
                    workcenter = operation.workcenter_id
                    capacity = max(workcenter.default_capacity, 1.0)
                    cycles = ceil(line.planned_production_qty / capacity)
                    planned_by_key[(workcenter.id, line.period_date)] += (
                        operation.time_cycle * cycles + workcenter.time_start + workcenter.time_stop
                    ) / 60.0
            workcenters = self.env["mrp.workcenter"].browse(
                list({workcenter_id for workcenter_id, period_date in planned_by_key})
            )
            period_dates = sorted({period_date for workcenter_id, period_date in planned_by_key})
            available_by_key, working_intervals, period_bounds = plan._get_calendar_capacity_hours(
                workcenters, period_dates
            )
            maintenance_by_key = plan._get_maintenance_hours(
                workcenters, working_intervals, period_bounds
            )
            values_by_key = {}
            for key, planned_hours in planned_by_key.items():
                workcenter_id, period_date = key
                available_hours = available_by_key.get(key, 0.0)
                maintenance_hours = maintenance_by_key.get(key, 0.0)
                effective_hours = max(0.0, available_hours - maintenance_hours)
                load_percent = planned_hours / effective_hours * 100.0 if effective_hours else 0.0
                status = plan._capacity_status(
                    load_percent,
                    plan.capacity_warning_threshold,
                    plan.capacity_overload_threshold,
                    planned_hours,
                    effective_hours,
                )
                overload_hours = max(0.0, planned_hours - effective_hours)
                values_by_key[key] = {
                    "production_plan_id": plan.id,
                    "company_id": plan.company_id.id,
                    "workcenter_id": workcenter_id,
                    "period_date": period_date,
                    "available_hours": available_hours,
                    "planned_hours": planned_hours,
                    "maintenance_hours": maintenance_hours,
                    "effective_available_hours": effective_hours,
                    "capacity_load_percent": load_percent,
                    "status": status,
                    "overload_hours": overload_hours,
                    "recommendation": plan._capacity_recommendation(status, overload_hours),
                }
            existing = {
                (capacity.workcenter_id.id, capacity.period_date): capacity
                for capacity in plan.capacity_line_ids
            }
            stale_capacities = plan.capacity_line_ids.filtered(
                lambda capacity: (capacity.workcenter_id.id, capacity.period_date) not in values_by_key
            )
            for capacity in stale_capacities:
                if capacity.alert_id and capacity.alert_id.state != "resolved":
                    capacity.alert_id.sudo().action_resolve()
            stale_capacities.sudo().unlink()
            capacity_rows = self.env["mogen.sop.workcenter.capacity"]
            for key, values in values_by_key.items():
                if key in existing:
                    existing[key].sudo().write(values)
                    capacity_rows |= existing[key]
                else:
                    capacity_rows |= self.env["mogen.sop.workcenter.capacity"].sudo().create(values)
            for capacity in capacity_rows:
                plan._sync_capacity_alert(capacity)
            loadable_rows = capacity_rows.filtered("effective_available_hours")
            average_load = (
                sum(capacity.capacity_load_percent for capacity in loadable_rows) / len(loadable_rows)
                if loadable_rows
                else 0.0
            )
            plan._write_workflow_values({"average_capacity_load": average_load})
        return True

    def action_view_capacity(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Workcenter Capacity"),
            "res_model": "mogen.sop.workcenter.capacity",
            "view_mode": "tree,pivot,graph",
            "domain": [("production_plan_id", "=", self.id)],
            "context": {"search_default_group_workcenter": 1},
        }

    def action_view_capacity_alerts(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Capacity Alerts"),
            "res_model": "mogen.sop.alert",
            "view_mode": "tree,form",
            "domain": [
                ("plan_id", "=", self.sop_plan_id.id),
                ("alert_type", "=", "capacity"),
                ("state", "!=", "resolved"),
            ],
        }

    def action_review(self):
        return self._transition(("calculated",), "review")

    def action_approve(self):
        self._require_manager()
        return self._transition(
            ("review",),
            "approved",
            {"approved_by_id": self.env.user.id, "approved_date": fields.Datetime.now()},
        )

    def action_execute(self):
        self._require_manager()
        return self._transition(("approved",), "executed")

    def action_cancel(self):
        if any(plan.state == "approved" for plan in self):
            self._require_manager()
        return self._transition(("draft", "calculated", "review", "approved"), "cancelled")

    def action_reset_draft(self):
        return self._transition(("calculated", "review", "cancelled"), "draft")


class MogenSopProductionLine(models.Model):
    _name = "mogen.sop.production.line"
    _description = "S&OP Production Plan Line"
    _order = "period_date, product_id, id"
    _check_company_auto = True

    production_plan_id = fields.Many2one(
        "mogen.sop.production.plan", required=True, ondelete="cascade", index=True
    )
    sop_plan_id = fields.Many2one(related="production_plan_id.sop_plan_id", store=True, index=True)
    version_id = fields.Many2one(related="production_plan_id.version_id", store=True, index=True)
    company_id = fields.Many2one(related="production_plan_id.company_id", store=True, index=True)
    warehouse_id = fields.Many2one(related="production_plan_id.warehouse_id", store=True, index=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True, index=True)
    product_tmpl_id = fields.Many2one(related="product_id.product_tmpl_id", store=True, index=True)
    categ_id = fields.Many2one(related="product_id.categ_id", store=True, index=True)
    bom_id = fields.Many2one("mrp.bom", check_company=True)
    period_date = fields.Date(required=True, index=True)
    demand_qty = fields.Float(required=True, readonly=True)
    safety_stock_qty = fields.Float(required=True, readonly=True)
    free_stock_qty = fields.Float(required=True, readonly=True)
    incoming_mo_qty = fields.Float(required=True, readonly=True)
    required_production_qty = fields.Float(required=True, readonly=True)
    planned_production_qty = fields.Float(required=True, readonly=True)
    completed_qty = fields.Float(readonly=True)
    remaining_qty = fields.Float(compute="_compute_remaining_qty", store=True)
    batch_size = fields.Float(readonly=True)
    planned_start_date = fields.Date()
    planned_finish_date = fields.Date()
    manufacturing_lead_time = fields.Integer(related="bom_id.produce_delay", readonly=True)
    priority = fields.Selection(
        [("0", "Low"), ("1", "Normal"), ("2", "High"), ("3", "Urgent")],
        default="1",
        readonly=True,
    )
    state = fields.Selection(related="production_plan_id.state", store=True, readonly=True, index=True)
    recommendation_ids = fields.Many2many(
        "mogen.sop.recommendation",
        "mogen_sop_production_line_recommendation_rel",
        "line_id",
        "recommendation_id",
        readonly=True,
    )

    @api.depends("planned_production_qty", "completed_qty")
    def _compute_remaining_qty(self):
        for line in self:
            line.remaining_qty = max(0.0, line.planned_production_qty - line.completed_qty)

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Production lines are generated by the production calculation."))
        return super().create(vals_list)

    def write(self, values):
        if not self.env.su:
            raise AccessError(_("Production calculation lines cannot be edited directly."))
        return super().write(values)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Production calculation lines cannot be deleted directly."))
        return super().unlink()


class MogenSopMaterialRequirement(models.Model):
    _name = "mogen.sop.material.requirement"
    _description = "S&OP Material Requirement"
    _order = "required_date, component_id, id"
    _check_company_auto = True

    production_plan_id = fields.Many2one(
        "mogen.sop.production.plan", required=True, ondelete="cascade", index=True
    )
    production_line_id = fields.Many2one(
        "mogen.sop.production.line",
        string="Primary Production Line",
        required=True,
        ondelete="restrict",
        index=True,
    )
    production_line_ids = fields.Many2many(
        "mogen.sop.production.line",
        "mogen_sop_material_requirement_production_line_rel",
        "requirement_id",
        "production_line_id",
        string="Production Lines",
        readonly=True,
    )
    company_id = fields.Many2one("res.company", required=True, index=True)
    warehouse_id = fields.Many2one("stock.warehouse", required=True, check_company=True, index=True)
    parent_product_id = fields.Many2one("product.product", required=True, check_company=True)
    component_id = fields.Many2one(
        "product.product", required=True, check_company=True, index=True
    )
    bom_id = fields.Many2one("mrp.bom", string="Primary BOM", required=True, check_company=True)
    bom_ids = fields.Many2many(
        "mrp.bom",
        "mogen_sop_material_requirement_bom_rel",
        "requirement_id",
        "bom_id",
        string="BOM Trace",
        readonly=True,
    )
    required_qty = fields.Float(required=True, readonly=True)
    on_hand_qty = fields.Float(required=True, readonly=True)
    free_qty = fields.Float(required=True, readonly=True)
    incoming_qty = fields.Float(required=True, readonly=True)
    shortage_qty = fields.Float(required=True, readonly=True)
    required_date = fields.Date(required=True, index=True)
    status = fields.Selection(
        [("available", "Available"), ("partial", "Partial"), ("shortage", "Shortage")],
        required=True,
        readonly=True,
        index=True,
    )
    procurement_route = fields.Selection(
        [("purchase", "Purchase"), ("manufacture", "Manufacture"), ("transfer", "Transfer")],
        required=True,
        readonly=True,
    )
    recommendation_id = fields.Many2one(
        "mogen.sop.recommendation", readonly=True, check_company=True, copy=False
    )

    _sql_constraints = [
        (
            "unique_plan_component_date",
            "unique(production_plan_id, component_id, required_date)",
            "A component can have one material requirement per production plan and required date.",
        ),
    ]

    @api.constrains("production_plan_id", "production_line_id", "company_id", "warehouse_id")
    def _check_plan_relations(self):
        for requirement in self:
            if requirement.production_line_id.production_plan_id != requirement.production_plan_id:
                raise ValidationError(_("The primary production line must belong to the production plan."))
            if requirement.production_plan_id.company_id != requirement.company_id:
                raise ValidationError(_("The material requirement company must match its production plan."))
            if requirement.production_plan_id.warehouse_id != requirement.warehouse_id:
                raise ValidationError(_("The material requirement warehouse must match its production plan."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Material requirements are generated by the material calculation."))
        return super().create(vals_list)

    def write(self, values):
        if not self.env.su:
            raise AccessError(_("Material requirements are generated by the material calculation."))
        return super().write(values)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Material requirements are generated by the material calculation."))
        return super().unlink()


class MogenSopWorkcenterCapacity(models.Model):
    _name = "mogen.sop.workcenter.capacity"
    _description = "S&OP Workcenter Capacity"
    _order = "period_date, workcenter_id, id"
    _check_company_auto = True

    production_plan_id = fields.Many2one(
        "mogen.sop.production.plan", required=True, ondelete="cascade", index=True
    )
    company_id = fields.Many2one("res.company", required=True, index=True)
    workcenter_id = fields.Many2one(
        "mrp.workcenter", required=True, check_company=True, index=True
    )
    period_date = fields.Date(required=True, index=True)
    available_hours = fields.Float(required=True, readonly=True)
    planned_hours = fields.Float(required=True, readonly=True)
    maintenance_hours = fields.Float(required=True, readonly=True)
    effective_available_hours = fields.Float(required=True, readonly=True)
    capacity_load_percent = fields.Float(required=True, readonly=True)
    status = fields.Selection(
        [("available", "Available"), ("warning", "Warning"), ("overloaded", "Overloaded")],
        required=True,
        readonly=True,
        index=True,
    )
    overload_hours = fields.Float(required=True, readonly=True)
    recommendation = fields.Text(readonly=True)
    alert_id = fields.Many2one("mogen.sop.alert", readonly=True, copy=False)

    _sql_constraints = [
        (
            "unique_plan_workcenter_period",
            "unique(production_plan_id, workcenter_id, period_date)",
            "A workcenter can have one capacity row per production plan and period.",
        ),
    ]

    @api.constrains("production_plan_id", "company_id", "workcenter_id")
    def _check_plan_relations(self):
        for capacity in self:
            if capacity.production_plan_id.company_id != capacity.company_id:
                raise ValidationError(_("The capacity company must match its production plan."))
            if capacity.workcenter_id.company_id != capacity.company_id:
                raise ValidationError(_("The workcenter must belong to the capacity company."))

    @api.model_create_multi
    def create(self, vals_list):
        if not self.env.su:
            raise AccessError(_("Capacity rows are generated by the capacity calculation."))
        return super().create(vals_list)

    def write(self, values):
        if not self.env.su:
            raise AccessError(_("Capacity rows are generated by the capacity calculation."))
        return super().write(values)

    def unlink(self):
        if not self.env.su:
            raise AccessError(_("Capacity rows are generated by the capacity calculation."))
        return super().unlink()


class MrpWorkcenterProductivityLoss(models.Model):
    _inherit = "mrp.workcenter.productivity.loss"

    is_sop_maintenance = fields.Boolean(
        string="S&OP Maintenance Downtime",
        help="Include this availability loss as planned maintenance downtime in S&OP capacity planning.",
    )
