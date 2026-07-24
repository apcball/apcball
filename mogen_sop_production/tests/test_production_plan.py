from datetime import datetime, timedelta

from odoo import Command, fields
from odoo.tests.common import TransactionCase


class TestSopProductionPlan(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.company.id)], limit=1
        )
        cls.warehouse_two = cls.env["stock.warehouse"].create(
            {"name": "S&OP Second Warehouse", "code": "SP2", "company_id": cls.company.id}
        )
        cls.other_company = cls.env["res.company"].create({"name": "S&OP Production Other"})
        cls.other_warehouse = cls.env["stock.warehouse"].create(
            {"name": "S&OP Other Warehouse", "code": "SPO", "company_id": cls.other_company.id}
        )
        cls.product = cls.env["product.product"].create(
            {"name": "S&OP Production Product", "detailed_type": "product"}
        )
        cls.manager_user = cls.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "S&OP Production Manager",
                "login": "sop_production_manager_%s" % cls.env.cr.dbname,
                "company_id": cls.company.id,
                "company_ids": [Command.set(cls.company.ids)],
                "groups_id": [
                    Command.link(cls.env.ref("mogen_sop_core.group_sop_manager").id)
                ],
            }
        )

    def _sop_plan(self, company, warehouse):
        return self.env["mogen.sop.plan"].create(
            {
                "name": "S&OP %s" % warehouse.code,
                "company_id": company.id,
                "warehouse_ids": [Command.set(warehouse.ids)],
                "date_start": fields.Date.today(),
                "date_end": fields.Date.today() + timedelta(days=30),
            }
        )

    def _approved_recommendation(
        self, sop_plan, warehouse, quantity, required_date=None, product=None
    ):
        recommendation = self.env["mogen.sop.recommendation"].create(
            {
                "name": "Approved manufacture demand",
                "plan_id": sop_plan.id,
                "recommendation_type": "manufacture",
                "product_id": (product or self.product).id,
                "warehouse_id": warehouse.id,
                "quantity": quantity,
                "required_date": required_date or fields.Date.today() + timedelta(days=7),
            }
        )
        recommendation.with_user(self.manager_user).action_approve()
        return recommendation

    def _production_plan(self, sop_plan, warehouse):
        return self.env["mogen.sop.production.plan"].create(
            {
                "sop_plan_id": sop_plan.id,
                "company_id": sop_plan.company_id.id,
                "warehouse_id": warehouse.id,
                "date_start": fields.Date.today(),
                "date_end": fields.Date.today() + timedelta(days=30),
            }
        )

    def _bom(self, product, components, bom_type="normal", operations=None):
        return self.env["mrp.bom"].create(
            {
                "product_tmpl_id": product.product_tmpl_id.id,
                "product_uom_id": product.uom_id.id,
                "product_qty": 1.0,
                "type": bom_type,
                "bom_line_ids": [
                    Command.create(
                        {
                            "product_id": component.id,
                            "product_qty": quantity,
                            "product_uom_id": uom.id,
                        }
                    )
                    for component, quantity, uom in components
                ],
                "operation_ids": [
                    Command.create(
                        {
                            "name": name,
                            "workcenter_id": workcenter.id,
                            "time_mode": "manual",
                            "time_cycle_manual": cycle_minutes,
                        }
                    )
                    for name, workcenter, cycle_minutes in (operations or [])
                ],
            }
        )

    def _workcenter(self, name, capacity=1.0, setup_minutes=0.0, cleanup_minutes=0.0):
        calendar = self.env["resource.calendar"].create(
            {
                "name": "%s Calendar" % name,
                "company_id": self.company.id,
                "attendance_ids": [
                    Command.create(
                        {"name": "Capacity shift", "dayofweek": str(day), "hour_from": 8.0, "hour_to": 16.0}
                    )
                    for day in range(7)
                ],
            }
        )
        return self.env["mrp.workcenter"].create(
            {
                "name": name,
                "company_id": self.company.id,
                "resource_calendar_id": calendar.id,
                "default_capacity": capacity,
                "time_start": setup_minutes,
                "time_stop": cleanup_minutes,
            }
        )

    def test_required_production_formula(self):
        plan_model = self.env["mogen.sop.production.plan"]
        self.assertEqual(
            plan_model._required_production_qty(12.0, 5.0, 7.0, 3.0),
            7.0,
        )
        self.assertEqual(
            plan_model._required_production_qty(3.0, 2.0, 6.0, 1.0),
            0.0,
        )

    def test_rounding_priority(self):
        plan_model = self.env["mogen.sop.production.plan"]
        self.assertEqual(plan_model._round_production_qty(11.0, 5.0, 4.0, 1.0), 15.0)
        self.assertEqual(plan_model._round_production_qty(11.0, 0.0, 4.0, 1.0), 12.0)
        self.assertEqual(plan_model._round_production_qty(11.2, 0.0, 0.0, 0.5), 11.5)

    def test_calculation_is_company_and_warehouse_specific(self):
        sop_plan = self._sop_plan(self.company, self.warehouse)
        sop_plan.write(
            {"warehouse_ids": [Command.set([self.warehouse.id, self.warehouse_two.id])]}
        )
        self._approved_recommendation(sop_plan, self.warehouse, 8.0)
        self._approved_recommendation(sop_plan, self.warehouse_two, 8.0)
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 3.0
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse_two.lot_stock_id, 10.0
        )

        first_plan = self._production_plan(sop_plan, self.warehouse)
        second_plan = self._production_plan(sop_plan, self.warehouse_two)
        first_plan.action_calculate_production()
        second_plan.action_calculate_production()

        self.assertEqual(first_plan.line_ids.required_production_qty, 5.0)
        self.assertEqual(second_plan.line_ids.required_production_qty, 0.0)
        self.assertEqual(first_plan.line_ids.free_stock_qty, 3.0)
        self.assertEqual(second_plan.line_ids.free_stock_qty, 10.0)

    def test_production_plan_company_record_rule(self):
        own_sop_plan = self._sop_plan(self.company, self.warehouse)
        other_sop_plan = self._sop_plan(self.other_company, self.other_warehouse)
        own_plan = self._production_plan(own_sop_plan, self.warehouse)
        other_plan = self._production_plan(other_sop_plan, self.other_warehouse)
        planner = self.env["res.users"].with_context(no_reset_password=True).create(
            {
                "name": "S&OP Production Planner",
                "login": "sop_production_planner_%s" % self.env.cr.dbname,
                "company_id": self.company.id,
                "company_ids": [Command.set(self.company.ids)],
                "groups_id": [
                    Command.link(self.env.ref("mogen_sop_production.group_sop_production_planner").id)
                ],
            }
        )
        visible_plans = self.env["mogen.sop.production.plan"].with_user(planner).search([])
        self.assertIn(own_plan, visible_plans)
        self.assertNotIn(other_plan, visible_plans)

    def test_periods_allocate_warehouse_stock_once(self):
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(
            sop_plan, self.warehouse, 3.0, fields.Date.today() + timedelta(days=7)
        )
        self._approved_recommendation(
            sop_plan, self.warehouse, 3.0, fields.Date.today() + timedelta(days=14)
        )
        self.env["stock.quant"]._update_available_quantity(
            self.product, self.warehouse.lot_stock_id, 5.0
        )
        production_plan = self._production_plan(sop_plan, self.warehouse)
        production_plan.action_calculate_production()
        self.assertEqual(production_plan.line_ids.mapped("required_production_qty"), [0.0, 1.0])

    def test_material_requirements_single_level_bom_and_shortage(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Finished Single", "detailed_type": "product"}
        )
        component = self.env["product.product"].create(
            {"name": "S&OP Component Single", "detailed_type": "product"}
        )
        self._bom(finished, [(component, 2.0, component.uom_id)])
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 6.0, product=finished)
        self.env["stock.quant"]._update_available_quantity(
            component, self.warehouse.lot_stock_id, 3.0
        )
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        requirement = production_plan.material_line_ids
        self.assertEqual(requirement.component_id, component)
        self.assertEqual(requirement.required_qty, 12.0)
        self.assertEqual(requirement.free_qty, 3.0)
        self.assertEqual(requirement.shortage_qty, 9.0)
        self.assertEqual(requirement.status, "partial")
        self.assertEqual(requirement.production_line_ids, production_plan.line_ids)

    def test_material_requirements_expand_multi_level_normal_boms(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Finished Multi", "detailed_type": "product"}
        )
        intermediate = self.env["product.product"].create(
            {"name": "S&OP Intermediate Multi", "detailed_type": "product"}
        )
        component = self.env["product.product"].create(
            {"name": "S&OP Component Multi", "detailed_type": "product"}
        )
        self._bom(finished, [(intermediate, 2.0, intermediate.uom_id)])
        self._bom(intermediate, [(component, 3.0, component.uom_id)])
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 4.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        requirement = production_plan.material_line_ids
        self.assertEqual(requirement.component_id, component)
        self.assertEqual(requirement.required_qty, 24.0)

    def test_material_requirements_aggregate_shared_components(self):
        first_finished = self.env["product.product"].create(
            {"name": "S&OP Finished Shared A", "detailed_type": "product"}
        )
        second_finished = self.env["product.product"].create(
            {"name": "S&OP Finished Shared B", "detailed_type": "product"}
        )
        component = self.env["product.product"].create(
            {"name": "S&OP Component Shared", "detailed_type": "product"}
        )
        self._bom(first_finished, [(component, 2.0, component.uom_id)])
        self._bom(second_finished, [(component, 3.0, component.uom_id)])
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 2.0, product=first_finished)
        self._approved_recommendation(sop_plan, self.warehouse, 2.0, product=second_finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        requirement = production_plan.material_line_ids
        self.assertEqual(len(requirement), 1)
        self.assertEqual(requirement.required_qty, 10.0)
        self.assertEqual(len(requirement.production_line_ids), 2)

    def test_material_requirements_convert_component_uom(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Finished UOM", "detailed_type": "product"}
        )
        component = self.env["product.product"].create(
            {"name": "S&OP Component UOM", "detailed_type": "product"}
        )
        dozen = self.env.ref("uom.product_uom_dozen")
        self._bom(finished, [(component, 1.0, dozen)])
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 2.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        self.assertEqual(production_plan.material_line_ids.required_qty, 24.0)

    def test_material_requirements_convert_incoming_purchase_uom(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Finished Incoming UOM", "detailed_type": "product"}
        )
        component = self.env["product.product"].create(
            {"name": "S&OP Component Incoming UOM", "detailed_type": "product"}
        )
        dozen = self.env.ref("uom.product_uom_dozen")
        self._bom(finished, [(component, 12.0, component.uom_id)])
        purchase_order = self.env["purchase.order"].create(
            {
                "partner_id": self.env.ref("base.res_partner_1").id,
                "company_id": self.company.id,
                "picking_type_id": self.warehouse.in_type_id.id,
                "order_line": [
                    Command.create(
                        {
                            "product_id": component.id,
                            "product_qty": 1.0,
                            "product_uom": dozen.id,
                            "price_unit": 1.0,
                        }
                    )
                ],
            }
        )
        purchase_order.button_confirm()
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 2.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        requirement = production_plan.material_line_ids
        self.assertEqual(requirement.required_qty, 24.0)
        self.assertEqual(requirement.incoming_qty, 12.0)
        self.assertEqual(requirement.shortage_qty, 12.0)

    def test_material_recommendations_are_draft_idempotent_and_reconciled(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Finished Recommendation", "detailed_type": "product"}
        )
        component = self.env["product.product"].create(
            {"name": "S&OP Component Recommendation", "detailed_type": "product"}
        )
        self._bom(finished, [(component, 2.0, component.uom_id)])
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 6.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)
        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        production_plan.with_user(self.manager_user).action_generate_material_recommendations()
        requirement = production_plan.material_line_ids
        recommendation = requirement.recommendation_id
        self.assertEqual(recommendation.state, "draft")
        self.assertEqual(recommendation.quantity, 12.0)
        self.assertEqual(recommendation.create_uid, self.manager_user)
        production_plan.with_user(self.manager_user).action_generate_material_recommendations()
        self.assertEqual(requirement.recommendation_id, recommendation)
        self.env["stock.quant"]._update_available_quantity(
            component, self.warehouse.lot_stock_id, 12.0
        )

        production_plan.action_calculate_material_requirements()

        self.assertFalse(production_plan.material_line_ids.recommendation_id)
        self.assertFalse(recommendation.exists())

    def test_material_requirements_follow_phantom_bom_behavior(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Finished Phantom", "detailed_type": "product"}
        )
        kit = self.env["product.product"].create(
            {"name": "S&OP Kit Phantom", "detailed_type": "product"}
        )
        component = self.env["product.product"].create(
            {"name": "S&OP Component Phantom", "detailed_type": "product"}
        )
        self._bom(finished, [(kit, 2.0, kit.uom_id)])
        self._bom(kit, [(component, 3.0, component.uom_id)], bom_type="phantom")
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 2.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        self.assertEqual(production_plan.material_line_ids.component_id, component)
        self.assertEqual(production_plan.material_line_ids.required_qty, 12.0)

    def test_material_requirements_skip_production_line_without_bom(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Finished Without BOM", "detailed_type": "product"}
        )
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 2.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_material_requirements()

        self.assertFalse(production_plan.material_line_ids)

    def test_material_requirements_reject_recursive_boms(self):
        first = self.env["product.product"].create(
            {"name": "S&OP Recursive A", "detailed_type": "product"}
        )
        second = self.env["product.product"].create(
            {"name": "S&OP Recursive B", "detailed_type": "product"}
        )
        self._bom(first, [(second, 1.0, second.uom_id)])
        second_bom = self._bom(second, [(self.product, 1.0, self.product.uom_id)])
        # Odoo prevents cycles at BOM maintenance time. Deliberately corrupt
        # the isolated test fixture to verify the planning guard as well.
        self.env.cr.execute(
            "UPDATE mrp_bom_line SET product_id = %s WHERE id = %s",
            [first.id, second_bom.bom_line_ids.id],
        )
        self.env.invalidate_all()
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 1.0, product=first)
        production_plan = self._production_plan(sop_plan, self.warehouse)
        production_plan.action_calculate_production()

        with self.assertRaisesRegex(Exception, "Recursive BOM"):
            production_plan.action_calculate_material_requirements()

    def test_capacity_calculates_operation_hours_and_calendar_availability(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Capacity Finished", "detailed_type": "product"}
        )
        workcenter = self._workcenter("S&OP Capacity WC", capacity=2.0, setup_minutes=30.0, cleanup_minutes=15.0)
        self._bom(
            finished,
            [],
            operations=[("S&OP Capacity Operation", workcenter, 60.0)],
        )
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 4.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_capacity()

        capacity = production_plan.capacity_line_ids
        self.assertEqual(capacity.workcenter_id, workcenter)
        self.assertEqual(capacity.planned_hours, 2.75)
        self.assertEqual(capacity.available_hours, 16.0)
        self.assertEqual(capacity.effective_available_hours, 16.0)
        self.assertEqual(capacity.capacity_load_percent, 17.1875)
        self.assertEqual(capacity.status, "available")

    def test_capacity_reduces_availability_for_maintenance_downtime(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Capacity Maintenance Finished", "detailed_type": "product"}
        )
        workcenter = self._workcenter("S&OP Maintenance WC")
        self._bom(finished, [], operations=[("Run", workcenter, 60.0)])
        loss_type = self.env["mrp.workcenter.productivity.loss.type"].create(
            {"loss_type": "availability"}
        )
        loss = self.env["mrp.workcenter.productivity.loss"].create(
            {"name": "Planned maintenance", "loss_id": loss_type.id, "is_sop_maintenance": True}
        )
        required_date = fields.Date.today() + timedelta(days=7)
        today = fields.Date.to_date(required_date)
        self.env["mrp.workcenter.productivity"].create(
            {
                "workcenter_id": workcenter.id,
                "loss_id": loss.id,
                "date_start": datetime.combine(today, datetime.min.time()).replace(hour=10),
                "date_end": datetime.combine(today, datetime.min.time()).replace(hour=12),
            }
        )
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(
            sop_plan, self.warehouse, 1.0, required_date=required_date, product=finished
        )
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_capacity()

        capacity = production_plan.capacity_line_ids
        self.assertEqual(capacity.available_hours, 8.0)
        self.assertEqual(capacity.maintenance_hours, 2.0)
        self.assertEqual(capacity.effective_available_hours, 6.0)

    def test_capacity_statuses_handle_warning_overload_and_zero_capacity(self):
        plan_model = self.env["mogen.sop.production.plan"]
        self.assertEqual(plan_model._capacity_status(84.99, 85.0, 100.0, 1.0, 1.0), "available")
        self.assertEqual(plan_model._capacity_status(85.0, 85.0, 100.0, 1.0, 1.0), "warning")
        self.assertEqual(plan_model._capacity_status(100.01, 85.0, 100.0, 1.0, 1.0), "overloaded")
        self.assertEqual(plan_model._capacity_status(0.0, 85.0, 100.0, 0.0, 0.0), "available")
        self.assertEqual(plan_model._capacity_status(0.0, 85.0, 100.0, 2.0, 0.0), "overloaded")

    def test_capacity_overload_creates_linked_alert_and_recommendation(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Capacity Overload Finished", "detailed_type": "product"}
        )
        workcenter = self._workcenter("S&OP Overload WC")
        self._bom(finished, [], operations=[("Long operation", workcenter, 600.0)])
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 1.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_capacity()

        capacity = production_plan.capacity_line_ids
        self.assertEqual(capacity.status, "overloaded")
        self.assertEqual(capacity.overload_hours, 2.0)
        self.assertEqual(capacity.alert_id.alert_type, "capacity")
        self.assertEqual(capacity.alert_id.severity, "critical")
        self.assertIn("Increase available capacity", capacity.recommendation)

    def test_capacity_ignores_non_maintenance_and_outside_shift_downtime(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Capacity Shift Finished", "detailed_type": "product"}
        )
        workcenter = self._workcenter("S&OP Shift WC")
        self._bom(finished, [], operations=[("Run", workcenter, 60.0)])
        required_date = fields.Date.today() + timedelta(days=7)
        loss_type = self.env["mrp.workcenter.productivity.loss.type"].create(
            {"loss_type": "availability"}
        )
        maintenance_loss = self.env["mrp.workcenter.productivity.loss"].create(
            {"name": "Planned maintenance", "loss_id": loss_type.id, "is_sop_maintenance": True}
        )
        breakdown_loss = self.env["mrp.workcenter.productivity.loss"].create(
            {"name": "Breakdown", "loss_id": loss_type.id}
        )
        day_start = datetime.combine(fields.Date.to_date(required_date), datetime.min.time())
        for loss, start_hour, end_hour in ((maintenance_loss, 20, 22), (breakdown_loss, 10, 12)):
            self.env["mrp.workcenter.productivity"].create(
                {
                    "workcenter_id": workcenter.id,
                    "loss_id": loss.id,
                    "date_start": day_start.replace(hour=start_hour),
                    "date_end": day_start.replace(hour=end_hour),
                }
            )
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(
            sop_plan, self.warehouse, 1.0, required_date=required_date, product=finished
        )
        production_plan = self._production_plan(sop_plan, self.warehouse)

        production_plan.action_calculate_production()
        production_plan.action_calculate_capacity()

        self.assertEqual(production_plan.capacity_line_ids.maintenance_hours, 0.0)

    def test_capacity_zero_calendar_overloads_and_stale_alerts_are_resolved(self):
        finished = self.env["product.product"].create(
            {"name": "S&OP Capacity Zero Finished", "detailed_type": "product"}
        )
        workcenter = self._workcenter("S&OP Zero WC")
        bom = self._bom(finished, [], operations=[("Long operation", workcenter, 600.0)])
        sop_plan = self._sop_plan(self.company, self.warehouse)
        self._approved_recommendation(sop_plan, self.warehouse, 1.0, product=finished)
        production_plan = self._production_plan(sop_plan, self.warehouse)
        production_plan.action_calculate_production()
        production_plan.action_calculate_capacity()
        alert = production_plan.capacity_line_ids.alert_id
        workcenter.resource_calendar_id = False

        production_plan.action_calculate_capacity()

        capacity = production_plan.capacity_line_ids
        self.assertEqual(capacity.status, "overloaded")
        self.assertEqual(capacity.effective_available_hours, 0.0)
        self.assertEqual(capacity.capacity_load_percent, 0.0)
        self.assertEqual(production_plan.average_capacity_load, 0.0)
        bom.operation_ids.unlink()
        production_plan.action_calculate_capacity()
        self.assertFalse(production_plan.capacity_line_ids)
        self.assertEqual(alert.state, "resolved")
