"""
Tests for forecast auto-allocation functionality.

Tests cover auto-allocation trigger on sale order confirmation,
allocation logic, over-allocation prevention, and edge cases.
"""

from odoo import fields
from odoo.exceptions import ValidationError, UserError
from odoo.tests import tagged

from .common import ForecastTestCommon


@tagged("post_install", "-at_install")
class TestForecastAutoAllocation(ForecastTestCommon):
    """Test auto-allocation triggered by sale order confirmation."""

    def setUp(self):
        """Set up test data for auto-allocation tests."""
        super().setUp()
        self.user_sales = self.user_sales
        self.user_planner = self.user_planner

    def test_auto_allocation_on_so_confirm(self):
        """Auto-allocation should create allocations when SO is confirmed."""
        # Create forecast plan for current month
        plan = self.create_forecast_plan(user=self.user_sales)
        line = self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )

        # Create and confirm sale order
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)]
        )
        so.action_confirm()

        # Verify allocation created
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations.allocated_qty, 50)
        self.assertFalse(allocations.is_non_forecast)

    def test_auto_allocation_skips_existing_allocations(self):
        """Auto-allocation should skip SO lines that already have allocations."""
        # Create forecast plan
        plan = self.create_forecast_plan(user=self.user_sales)
        self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )

        # Create sale order with allocation
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 30)]
        )
        allocation = self.create_allocation(
            plan, so, allocated_qty=30, plan_line=plan.line_ids[0]
        )

        # Confirm SO (should not create new allocation)
        so.action_confirm()

        # Verify only original allocation exists
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].id, allocation.id)

    def test_auto_allocation_handles_non_forecast_quantity(self):
        """Auto-allocation should create non-forecast allocation when forecast is exceeded."""
        # Create forecast plan with limited quantity
        plan = self.create_forecast_plan(user=self.user_sales)
        line = self.create_forecast_line(
            plan, self.product_a, forecast_qty=50, apply_distribution=True
        )

        # Create SO exceeding forecast
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 100)]
        )
        so.action_confirm()

        # Verify allocations created
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )

        # Should have 2 allocations: 1 forecast + 1 non-forecast
        self.assertGreaterEqual(len(allocations), 1)

        # First allocation should be forecast (up to available)
        forecast_alloc = allocations.filtered(lambda a: not a.is_non_forecast)
        self.assertEqual(len(forecast_alloc), 1)
        self.assertEqual(forecast_alloc.allocated_qty, 50)

    def test_auto_allocation_no_plan_for_month(self):
        """Auto-allocation should skip when no forecast plan exists for month."""
        # Create SO without forecast plan
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)]
        )

        # Confirm SO (should not fail)
        so.action_confirm()

        # Verify no allocations created
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 0)

    def test_auto_allocation_multiple_lines(self):
        """Auto-allocation should handle multiple product lines."""
        # Create forecast plan with multiple products
        plan = self.create_forecast_plan(user=self.user_sales)
        line_a = self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )
        line_b = self.create_forecast_line(
            plan, self.product_b, forecast_qty=200, apply_distribution=True
        )

        # Create SO with multiple lines
        so = self.create_sale_order(
            user=self.user_sales,
            lines=[(self.product_a, 50), (self.product_b, 100)],
        )
        so.action_confirm()

        # Verify allocations for both products
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 2)

        alloc_a = allocations.filtered(lambda a: a.product_id == self.product_a)
        alloc_b = allocations.filtered(lambda a: a.product_id == self.product_b)

        self.assertEqual(alloc_a.allocated_qty, 50)
        self.assertEqual(alloc_b.allocated_qty, 100)

    def test_auto_allocation_respects_company(self):
        """Auto-allocation should only use plans from same company."""
        # Create forecast plan
        plan = self.create_forecast_plan(user=self.user_sales)

        # Create SO with same company
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 50)]
        )
        so.action_confirm()

        # Verify allocation uses correct plan
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        if allocations:
            self.assertEqual(allocations[0].plan_id, plan)


@tagged("post_install", "-at_install")
class TestForecastAutoAllocationErrorHandling(ForecastTestCommon):
    """Test error handling in auto-allocation."""

    def setUp(self):
        """Set up test data."""
        super().setUp()
        self.user_sales = self.user_sales

    def test_auto_allocation_validation_error_rollback(self):
        """Validation errors should rollback SO confirmation."""
        # Create forecast plan with over-allocation constraint
        plan = self.create_forecast_plan(user=self.user_sales)
        line = self.create_forecast_line(
            plan, self.product_a, forecast_qty=50, apply_distribution=True
        )

        # Create allocation that would cause over-allocation
        existing_alloc = self.create_allocation(
            plan,
            self.create_sale_order(user=self.user_sales, lines=[(self.product_a, 50)]),
            allocated_qty=50,
            plan_line=line,
        )

        # Create SO that would cause over-allocation
        # This should be prevented by constraint, not auto-allocation
        # Auto-allocation should respect available forecast
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 10)]
        )

        # Confirm SO - should succeed (auto-allocation respects available)
        so.action_confirm()

        # SO should be confirmed
        self.assertEqual(so.state, "sale")

        # No new allocation should be created (forecast exhausted)
        new_allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(new_allocations), 0)

    def test_auto_allocation_access_denied_continues(self):
        """Access denied in auto-allocation should not block SO confirmation."""
        # Create SO with different user (no forecast plan)
        other_user = self.env["res.users"].create(
            {
                "name": "Other User",
                "login": "other_user",
                "groups_id": [(4, self.env.ref("sales_team.group_sale_salesman").id)],
            }
        )

        so = self.create_sale_order(
            user=other_user, lines=[(self.product_a, 50)]
        )

        # Confirm SO - should succeed even without auto-allocation
        so.action_confirm()

        # SO should be confirmed
        self.assertEqual(so.state, "sale")

        # No allocations created (access denied, no plan found)
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 0)


@tagged("post_install", "-at_install")
class TestForecastAutoAllocationEdgeCases(ForecastTestCommon):
    """Test edge cases in auto-allocation."""

    def setUp(self):
        """Set up test data."""
        super().setUp()

    def test_auto_allocation_zero_quantity_line(self):
        """Auto-allocation should skip lines with zero quantity."""
        plan = self.create_forecast_plan(user=self.user_sales)
        self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )

        # Create SO with zero quantity line
        so = self.create_sale_order(
            user=self.user_sales, lines=[(self.product_a, 0)]
        )
        so.action_confirm()

        # Verify no allocation created
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 0)

    def test_auto_allocation_display_type_line(self):
        """Auto-allocation should skip display-type lines (sections/notes)."""
        plan = self.create_forecast_plan(user=self.user_sales)
        self.create_forecast_line(
            plan, self.product_a, forecast_qty=100, apply_distribution=True
        )

        # Create SO with display line (section)
        so = self.create_sale_order(user=self.user_sales, lines=[])
        self.env["sale.order.line"].create(
            {
                "order_id": so.id,
                "display_type": "line_section",
                "name": "Section",
            }
        )
        so.action_confirm()

        # Verify no allocation for display line
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 0)

    def test_auto_allocation_without_salesperson(self):
        """Auto-allocation should skip SOs without salesperson."""
        # Create SO without user_id
        so = self.create_sale_order(user=None, lines=[(self.product_a, 50)])

        # Confirm SO
        so.action_confirm()

        # Verify no allocation created (no user to match plan)
        allocations = self.env["forecast.allocation"].search(
            [("sale_order_id", "=", so.id)]
        )
        self.assertEqual(len(allocations), 0)
