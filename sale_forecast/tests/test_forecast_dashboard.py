"""
Tests for forecast dashboard functionality.

Tests cover dashboard data loading, KPI calculations,
and dashboard-specific business logic.
"""

from odoo import fields
from odoo.tests import tagged

from .common import ForecastTestCommon


@tagged("post_install", "-at_install")
class TestForecastDashboard(ForecastTestCommon):
    """Test dashboard data loading and KPI calculations."""

    def setUp(self):
        """Set up test data for dashboard tests."""
        super().setUp()
        # Create comprehensive test data
        self.plan = self.create_forecast_plan(user=self.user_planner)
        self.plan2 = self.create_forecast_plan(user=self.user_sales)

        # Create forecast lines
        self.line1 = self.create_forecast_line(
            self.plan, self.product_a, forecast_qty=100, apply_distribution=True
        )
        self.line2 = self.create_forecast_line(
            self.plan, self.product_b, forecast_qty=200, apply_distribution=True
        )
        self.line3 = self.create_forecast_line(
            self.plan2, self.product_c, forecast_qty=150, apply_distribution=True
        )

        # Create sale orders
        self.so1 = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)], state="sale"
        )
        self.so2 = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_b, 100)], state="sale"
        )
        self.so3 = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_c, 75)], state="sale"
        )

    def test_dashboard_data_loading(self):
        """Dashboard should load successfully with test data."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Verify KPI fields are populated
        self.assertGreater(dashboard.total_forecast_qty_all, 0)
        self.assertGreater(dashboard.total_allocated_qty, 0)
        self.assertGreaterEqual(dashboard.allocation_rate, 0)

    def test_dashboard_total_forecast_calculation(self):
        """Total forecast should sum all forecast quantities."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Expected: 100 + 200 + 150 = 450
        expected_forecast = 450.0
        self.assertEqual(dashboard.total_forecast_qty_all, expected_forecast)

    def test_dashboard_monthly_metrics(self):
        """Monthly metrics should show data by month."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Should have monthly metrics
        self.assertGreater(len(dashboard.monthly_metric_ids), 0)

        # Monthly metrics should have required fields
        for metric in dashboard.monthly_metric_ids:
            self.assertIsNotNone(metric.month)
            self.assertIsNotNone(metric.forecast_qty)

    def test_dashboard_product_metrics(self):
        """Product metrics should show top allocated products."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Should have product metrics
        self.assertGreater(len(dashboard.product_metric_ids), 0)

        # Product metrics should be sorted by allocated_qty desc
        allocated_qtys = [p.allocated_qty for p in dashboard.product_metric_ids]
        self.assertEqual(allocated_qtys, sorted(allocated_qtys, reverse=True))

    def test_dashboard_recent_plans(self):
        """Recent plans should show latest plans."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Should show up to 6 recent plans
        self.assertLessEqual(len(dashboard.recent_plan_ids), 6)

        # Recent plans should have required fields
        for plan in dashboard.recent_plan_ids:
            self.assertIsNotNone(plan.plan_id)
            self.assertIsNotNone(plan.name)
            self.assertIsNotNone(plan.state)

    def test_dashboard_weekly_distribution(self):
        """Weekly distribution should show forecast by week."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Should have weekly distribution data
        self.assertGreater(len(dashboard.weekly_distribution_ids), 0)

        # Weekly distribution should be grouped by month
        months = set(w.arrival_month for w in dashboard.weekly_distribution_ids)
        self.assertGreater(len(months), 0)

    def test_dashboard_allocation_rate(self):
        """Allocation rate should be calculated correctly."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Allocation rate = (allocated / forecast) * 100
        if dashboard.total_forecast_qty_all > 0:
            expected_rate = (
                dashboard.total_allocated_qty / dashboard.total_forecast_qty_all * 100.0
            )
            self.assertAlmostEqual(dashboard.allocation_rate, expected_rate, places=2)
        else:
            self.assertEqual(dashboard.allocation_rate, 0.0)

    def test_dashboard_accuracy_rate(self):
        """Forecast accuracy should be calculated correctly."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Accuracy rate = (actual / forecast) * 100
        if dashboard.total_forecast_qty_all > 0:
            expected_accuracy = (
                dashboard.total_actual_sold_qty / dashboard.total_forecast_qty_all * 100.0
            )
            self.assertAlmostEqual(dashboard.forecast_accuracy_rate, expected_accuracy, places=2)
        else:
            self.assertEqual(dashboard.forecast_accuracy_rate, 0.0)


@tagged("post_install", "-at_install")
class TestForecastDashboardWithAllocations(ForecastTestCommon):
    """Test dashboard with allocations created."""

    def setUp(self):
        """Set up test data with allocations."""
        super().setUp()
        self.plan = self.create_forecast_plan(user=self.user_planner)
        self.line = self.create_forecast_line(
            self.plan, self.product_a, forecast_qty=100, apply_distribution=True
        )

        # Create sale order with allocation
        self.so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)], state="sale"
        )
        self.allocation = self.create_allocation(
            self.plan, self.so, allocated_qty=50, plan_line=self.line
        )

    def test_dashboard_with_allocations(self):
        """Dashboard should reflect allocations correctly."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Allocations should be counted in totals
        self.assertGreater(dashboard.total_allocated_qty, 0)

    def test_dashboard_recent_allocations(self):
        """Recent allocations should show latest allocations."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # Should show up to 8 recent allocations
        self.assertLessEqual(len(dashboard.recent_allocation_ids), 8)

        # Recent allocations should have required fields
        for alloc in dashboard.recent_allocation_ids:
            self.assertIsNotNone(alloc.allocation_id)
            self.assertIsNotNone(alloc.name)
            self.assertIsNotNone(alloc.state)


@tagged("post_install", "-at_install")
class TestForecastDashboardEdgeCases(ForecastTestCommon):
    """Test dashboard edge cases."""

    def test_dashboard_with_no_data(self):
        """Dashboard should load successfully with no data."""
        dashboard = self.env["sale.forecast.dashboard"].new()

        # KPIs should be zero or calculated correctly
        self.assertGreaterEqual(dashboard.total_forecast_qty_all, 0)
        self.assertGreaterEqual(dashboard.total_allocated_qty, 0)

    def test_dashboard_with_cancelled_plans(self):
        """Cancelled plans should not affect KPIs."""
        plan = self.create_forecast_plan(user=self.user_planner)
        line = self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )
        plan.state = "cancel"

        dashboard = self.env["sale.forecast.dashboard"].new()

        # Cancelled plan should not be included
        self.assertEqual(dashboard.total_forecast_qty_all, 0)

    def test_dashboard_with_cancelled_allocations(self):
        """Cancelled allocations should not be counted."""
        plan = self.create_forecast_plan(user=self.user_planner)
        line = self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )

        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)], state="sale"
        )
        allocation = self.create_allocation(
            plan, so, allocated_qty=50, plan_line=line
        )
        allocation.state = "cancel"

        dashboard = self.env["sale.forecast.dashboard"].new()

        # Cancelled allocation should not be counted
        self.assertEqual(dashboard.total_allocated_qty, 0)

    def test_dashboard_with_non_forecast_allocations(self):
        """Non-forecast allocations should not affect allocation rate."""
        plan = self.create_forecast_plan(user=self.user_planner)
        line = self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )

        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)], state="sale"
        )
        allocation = self.create_allocation(
            plan, so, allocated_qty=50, plan_line=line, is_non_forecast=True
        )

        dashboard = self.env["sale.forecast.dashboard"].new()

        # Non-forecast allocation should not count toward allocation rate
        self.assertEqual(dashboard.total_allocated_qty, 0)
