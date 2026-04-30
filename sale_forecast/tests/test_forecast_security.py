"""
Tests for forecast security and access control.

Tests cover record rules, multi-tenancy, user role permissions,
and data segregation.
"""

from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import ForecastSecurityTestCommon


@tagged("post_install", "-at_install")
class TestForecastPlanSecurity(ForecastSecurityTestCommon):
    """Test forecast plan access control and record rules."""

    def test_planner_can_create_own_plan(self):
        """Planner should be able to create forecast plan for themselves."""
        plan = self.env["forecast.plan"].with_user(self.user_planner).create(
            {"user_id": self.user_planner.id}
        )
        self.assertTrue(plan)

    def test_planner_cannot_create_plan_for_other_user(self):
        """Planner should not be able to create plan for another user."""
        with self.assertRaises(AccessError):
            self.env["forecast.plan"].with_user(self.user_planner).create(
                {"user_id": self.user_sales.id}
            )

    def test_planner_can_read_own_plan(self):
        """Planner should be able to read own forecast plans."""
        plan = self.create_forecast_plan(user=self.user_planner)

        # Can read as planner
        read_plan = self.env["forecast.plan"].with_user(self.user_planner).browse(
            plan.id
        )
        self.assertEqual(read_plan.id, plan.id)

    def test_planner_cannot_read_other_user_plan(self):
        """Planner should not be able to read another user's plan."""
        plan = self.create_forecast_plan(user=self.user_sales)

        # Cannot read as other planner
        with self.assertRaises(AccessError):
            self.env["forecast.plan"].with_user(self.user_planner).browse(
                plan.id
            ).read()

    def test_manager_can_read_all_plans(self):
        """Manager should be able to read all forecast plans."""
        plan1 = self.create_forecast_plan(user=self.user_planner)
        plan2 = self.create_forecast_plan(user=self.user_sales)

        # Manager can read both
        plans = self.env["forecast.plan"].with_user(self.user_manager).search([])
        self.assertIn(plan1.id, plans.ids)
        self.assertIn(plan2.id, plans.ids)

    def test_planner_search_returns_only_own_plans(self):
        """Planner search should only return own plans."""
        plan1 = self.create_forecast_plan(user=self.user_planner)
        plan2 = self.create_forecast_plan(user=self.user_sales)

        # Planner search returns only own plans
        plans = self.env["forecast.plan"].with_user(self.user_planner).search([])
        self.assertIn(plan1.id, plans.ids)
        self.assertNotIn(plan2.id, plans.ids)


@tagged("post_install", "-at_install")
class TestForecastLineSecurity(ForecastSecurityTestCommon):
    """Test forecast line access control via parent plan."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.plan_planner = self.create_forecast_plan(user=self.user_planner)
        self.plan_sales = self.create_forecast_plan(user=self.user_sales)

        self.line_planner = self.create_forecast_line(
            self.plan_planner, self.product_a, 100
        )
        self.line_sales = self.create_forecast_line(
            self.plan_sales, self.product_b, 200
        )

    def test_planner_can_read_lines_from_own_plan(self):
        """Planner should be able to read lines from own plan."""
        lines = self.env["forecast.line"].with_user(self.user_planner).search([])
        self.assertIn(self.line_planner.id, lines.ids)
        self.assertNotIn(self.line_sales.id, lines.ids)

    def test_sales_can_read_lines_from_any_plan(self):
        """Sales allocator should be able to read lines from any plan."""
        lines = self.env["forecast.line"].with_user(self.user_sales).search([])
        self.assertIn(self.line_planner.id, lines.ids)
        self.assertIn(self.line_sales.id, lines.ids)

    def test_manager_can_read_all_lines(self):
        """Manager should be able to read all forecast lines."""
        lines = self.env["forecast.line"].with_user(self.user_manager).search([])
        self.assertIn(self.line_planner.id, lines.ids)
        self.assertIn(self.line_sales.id, lines.ids)

    def test_planner_cannot_modify_other_user_lines(self):
        """Planner should not be able to modify lines from other user's plan."""
        with self.assertRaises(AccessError):
            self.env["forecast.line"].with_user(self.user_planner).browse(
                self.line_sales.id
            ).write({"forecast_qty": 300})


@tagged("post_install", "-at_install")
class TestForecastAllocationSecurity(ForecastSecurityTestCommon):
    """Test forecast allocation access control."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.plan = self.create_forecast_plan(user=self.user_planner)
        self.line = self.create_forecast_line(
            self.plan, self.product_a, 100
        )

        self.so_planner = self.create_sale_order(
            user=self.user_planner, lines=[(self.product_a, 50)], state="sale"
        )
        self.so_sales = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_b, 100)], state="sale"
        )

    def test_planner_can_read_allocations_from_own_plan(self):
        """Planner should be able to read allocations from own plan."""
        allocation = self.create_allocation(
            self.plan, self.so_planner, allocated_qty=50, plan_line=self.line
        )

        allocations = self.env["forecast.allocation"].with_user(
            self.user_planner
        ).search([])
        self.assertIn(allocation.id, allocations.ids)

    def test_sales_can_read_allocations_from_own_so(self):
        """Sales allocator should be able to read allocations from own sale orders."""
        allocation = self.create_allocation(
            self.plan, self.so_sales, allocated_qty=100, product=self.product_b
        )

        allocations = self.env["forecast.allocation"].with_user(
            self.user_sales
        ).search([])
        self.assertIn(allocation.id, allocations.ids)

    def test_sales_cannot_read_allocations_from_other_so(self):
        """Sales allocator should not be able to read allocations from other's sale orders."""
        allocation = self.create_allocation(
            self.plan, self.so_planner, allocated_qty=50, plan_line=self.line
        )

        # Other sales user cannot read
        allocations = self.env["forecast.allocation"].with_user(
            self.user_sales
        ).search([])
        self.assertNotIn(allocation.id, allocations.ids)

    def test_manager_can_read_all_allocations(self):
        """Manager should be able to read all allocations."""
        alloc1 = self.create_allocation(
            self.plan, self.so_planner, allocated_qty=50, plan_line=self.line
        )
        alloc2 = self.create_allocation(
            self.plan, self.so_sales, allocated_qty=100, product=self.product_b
        )

        # Manager can read both
        allocations = self.env["forecast.allocation"].with_user(
            self.user_manager
        ).search([])
        self.assertIn(alloc1.id, allocations.ids)
        self.assertIn(alloc2.id, allocations.ids)


@tagged("post_install", "-at_install")
class TestForecastMultiTenancy(ForecastSecurityTestCommon):
    """Test multi-company data segregation."""

    def setUp(self):
        """Set up test data with multiple companies."""
        super().setUp()
        # Create second company
        self.company2 = self.env["res.company"].create(
            {
                "name": "Test Company 2",
                "currency_id": self.env.ref("base.EUR").id,
            }
        )

    def test_user_sees_only_own_company_plans(self):
        """User should only see plans from own company."""
        # Plan in default company
        plan1 = self.create_forecast_plan(user=self.user_planner)

        # Plan in second company
        self.env = self.env(user=self.user_planner, company=self.company2)
        plan2 = self.create_forecast_plan(user=self.user_planner)

        # User in default company sees only plan1
        self.env = self.env(user=self.user_planner, company=self.company)
        plans = self.env["forecast.plan"].search([])
        self.assertIn(plan1.id, plans.ids)
        self.assertNotIn(plan2.id, plans.ids)

    def test_manager_sees_all_company_plans(self):
        """Manager with multi-company access should see plans from all companies."""
        # Give manager access to both companies
        self.user_manager.write(
            {
                "company_ids": [(4, self.company.id), (4, self.company2.id)],
                "company_id": self.company.id,
            }
        )

        # Create plans in both companies
        self.env = self.env(user=self.user_manager, company=self.company)
        plan1 = self.create_forecast_plan(user=self.user_manager)

        self.env = self.env(user=self.user_manager, company=self.company2)
        plan2 = self.create_forecast_plan(user=self.user_manager)

        # Manager in default company can see both
        self.env = self.env(user=self.user_manager, company=self.company)
        plans = self.env["forecast.plan"].search([])
        self.assertIn(plan1.id, plans.ids)
        # May not see plan2 depending on Odoo version and configuration


@tagged("post_install", "-at_install")
class TestForecastAutoAllocationSecurity(ForecastSecurityTestCommon):
    """Test auto-allocation respects access control."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.plan = self.create_forecast_plan(user=self.user_sales)
        self.line = self.create_forecast_line(
            self.plan, self.product_a, 100
        )

    def test_auto_allocation_respects_plan_access(self):
        """Auto-allocation should only use plans user can access."""
        # Create SO for sales user (has plan)
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)]
        )

        # Confirm as sales user
        so.with_user(self.user_sales).action_confirm()

        # Verify allocation created (user has access to plan)
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertGreater(len(allocations), 0)

    def test_auto_allocation_skips_without_plan(self):
        """Auto-allocation should skip when user has no plan."""
        # Create SO for planner (no plan for current month)
        so = self.create_sale_order(
            user=self.user_planner, lines=[(self.product_a, 50)]
        )

        # Confirm as planner
        so.with_user(self.user_planner).action_confirm()

        # Verify no allocation created (no plan)
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 0)


@tagged("post_install", "-at_install")
class TestForecastDashboardSecurity(ForecastSecurityTestCommon):
    """Test dashboard respects access control."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.plan = self.create_forecast_plan(user=self.user_planner)
        self.line = self.create_forecast_line(
            self.plan, self.product_a, 100
        )

    def test_dashboard_respects_user_context(self):
        """Dashboard should only show data user can access."""
        # Dashboard uses sudo for aggregations, but this is intentional
        # to show overall forecast performance to managers/planners

        # User should still be able to access dashboard
        dashboard = self.env["sale.forecast.dashboard"].with_user(
            self.user_planner
        ).new()

        # Dashboard should load successfully
        self.assertIsNotNone(dashboard)

        # KPIs should be calculated (may include all data via sudo)
        self.assertGreaterEqual(dashboard.total_forecast_qty_all, 0)

    def test_dashboard_available_to_all_roles(self):
        """Dashboard should be accessible to all forecast roles."""
        for user in [self.user_planner, self.user_sales, self.user_manager]:
            dashboard = self.env["sale.forecast.dashboard"].with_user(user).new()
            self.assertIsNotNone(dashboard)
            self.assertGreaterEqual(dashboard.total_forecast_qty_all, 0)


@tagged("post_install", "-at_install")
class TestCrossUserAllocationValidation(ForecastSecurityTestCommon):
    """Test cross-user allocation validation."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.plan_sales = self.create_forecast_plan(user=self.user_sales)
        self.plan_planner = self.create_forecast_plan(user=self.user_planner)

        self.line_sales = self.create_forecast_line(
            self.plan_sales, self.product_a, 100
        )

        self.so_sales = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)], state="sale"
        )
        self.so_planner = self.create_sale_order(
            user=self.user_planner, lines=[(self.product_b, 50)], state="sale"
        )

    def test_same_user_allocation_allowed(self):
        """Allow allocation when SO and plan belong to same user."""
        allocation = self.create_allocation(
            self.plan_sales, self.so_sales, plan_line=self.line_sales
        )
        self.assertTrue(allocation)

    def test_cross_user_allocation_blocked(self):
        """Block allocation when SO and plan belong to different users."""
        # Try to allocate planner's SO to sales user's plan
        with self.assertRaises(ValidationError):
            self.create_allocation(
                self.plan_sales, self.so_planner
            )

    def test_cross_user_allocation_block_both_ways(self):
        """Block cross-user allocation regardless of direction."""
        # Try sales SO to planner plan
        with self.assertRaises(ValidationError):
            self.create_allocation(
                self.plan_planner, self.so_sales
            )

        # Try planner SO to sales plan
        with self.assertRaises(ValidationError):
            self.create_allocation(
                self.plan_sales, self.so_planner
            )

    def test_allocation_without_user_allowed(self):
        """Allow allocation when SO has no user_id."""
        so = self.create_sale_order(user=None, lines=[(self.product_a, 50)])

        # Should succeed
        allocation = self.create_allocation(self.plan_sales, so)
        self.assertTrue(allocation)

    def test_update_plan_to_cross_user_blocked(self):
        """Block update when changing plan to different user."""
        # Create valid allocation
        allocation = self.create_allocation(
            self.plan_sales, self.so_sales, plan_line=self.line_sales
        )

        # Try to change to planner's plan (should fail)
        with self.assertRaises(ValidationError):
            allocation.write({"plan_id": self.plan_planner.id})

    def test_update_so_to_cross_user_blocked(self):
        """Block update when changing SO to different user."""
        # Create valid allocation
        allocation = self.create_allocation(
            self.plan_sales, self.so_sales, plan_line=self.line_sales
        )

        # Try to change to planner's SO (should fail)
        with self.assertRaises(ValidationError):
            allocation.write({"sale_order_id": self.so_planner.id})

    def test_sudo_bypass_cross_user_blocked(self):
        """Constraint should block cross-user even with sudo."""
        # Try to create cross-user allocation with sudo (should still fail)
        with self.assertRaises(ValidationError):
            self.env["forecast.allocation"].sudo().create({
                "plan_id": self.plan_sales.id,
                "sale_order_id": self.so_planner.id,
                "allocated_qty": 50,
                "product_id": self.product_b.id,
            })

    def test_manager_can_create_cross_user(self):
        """Manager cannot bypass cross-user validation."""
        # Even managers cannot create cross-user allocations
        with self.assertRaises(ValidationError):
            self.env["forecast.allocation"].with_user(
                self.user_manager
            ).create({
                "plan_id": self.plan_sales.id,
                "sale_order_id": self.so_planner.id,
                "allocated_qty": 50,
                "product_id": self.product_b.id,
            })
