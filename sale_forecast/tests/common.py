"""
Common test fixtures and helpers for sale_forecast module tests.

This module provides base test class with shared setup data for testing
forecast plans, lines, allocations, and auto-allocation functionality.
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class ForecastTestCommon(TransactionCase):
    """
    Common test class providing shared setup data for forecast module tests.
    All test classes should inherit from this to use pre-configured test data.
    """

    @classmethod
    def setUpClass(cls):
        """
        Set up common test data: users, products, partners, and sequences.
        This runs once before all tests in the class.
        """
        super().setUpClass()

        # Create test users with different forecast roles
        cls.user_planner = cls.env["res.users"].create(
            {
                "name": "Test Forecast Planner",
                "login": "test_planner",
                "email": "planner@test.com",
                "groups_id": [
                    (4, cls.env.ref("sale_forecast.group_sale_forecast_planner").id),
                    (4, cls.env.ref("base.group_user").id),
                ],
            }
        )

        cls.user_sales = cls.env["res.users"].create(
            {
                "name": "Test Sales Allocator",
                "login": "test_sales",
                "email": "sales@test.com",
                "groups_id": [
                    (4, cls.env.ref("sale_forecast.group_sale_forecast_sales").id),
                    (4, cls.env.ref("sales_team.group_sale_salesman").id),
                ],
            }
        )

        cls.user_manager = cls.env["res.users"].create(
            {
                "name": "Test Forecast Manager",
                "login": "test_manager",
                "email": "manager@test.com",
                "groups_id": [
                    (4, cls.env.ref("sale_forecast.group_sale_forecast_manager").id),
                    (4, cls.env.ref("sales_team.group_sale_manager").id),
                ],
            }
        )

        # Create test products (sale_ok=True required for forecast lines)
        cls.product_a = cls.env["product.product"].create(
            {
                "name": "Test Product A",
                "sale_ok": True,
                "lst_price": 100.0,
                "type": "product",
            }
        )

        cls.product_b = cls.env["product.product"].create(
            {
                "name": "Test Product B",
                "sale_ok": True,
                "lst_price": 200.0,
                "type": "product",
            }
        )

        cls.product_c = cls.env["product.product"].create(
            {
                "name": "Test Product C",
                "sale_ok": True,
                "lst_price": 300.0,
                "type": "product",
            }
        )

        # Create test customer partner
        cls.partner_customer = cls.env["res.partner"].create(
            {
                "name": "Test Customer",
                "email": "customer@test.com",
                "customer_rank": 1,
            }
        )

        # Get default company
        cls.company = cls.env.company

        # Store pricelist for SO creation
        cls.pricelist = cls.env["product.pricelist"].search([], limit=1)

    # --- Helper Methods ---

    def create_forecast_plan(self, user=None, start_date=None, state="draft"):
        """
        Create a forecast plan with default values.

        Args:
            user (res.users): User to assign as salesperson (defaults to user_planner)
            start_date (date): Start date (defaults to first of current month)
            state (str): Initial state (draft, confirmed, done, cancel)

        Returns:
            forecast.plan record
        """
        if user is None:
            user = self.user_planner

        plan_vals = {
            "user_id": user.id,
            "state": state,
            "company_id": self.company.id,
        }

        if start_date:
            plan_vals["start_date"] = start_date

        return self.env["forecast.plan"].create(plan_vals)

    def create_forecast_line(
        self,
        plan,
        product,
        forecast_qty,
        arrival_month=None,
        expected_week="1",
        apply_distribution=True,
    ):
        """
        Create a forecast line with optional auto weekly distribution.

        Args:
            plan (forecast.plan): Parent plan
            product (product.product): Product to forecast
            forecast_qty (float): Total forecast quantity
            arrival_month (date): Arrival month (defaults to current month)
            expected_week (str): Expected week (1-5, default "1")
            apply_distribution (bool): Auto-apply weekly distribution

        Returns:
            forecast.line record
        """
        from odoo import fields

        if arrival_month is None:
            arrival_month = fields.Date.start_of(fields.Date.context_today(self), "month")

        line_vals = {
            "plan_id": plan.id,
            "product_id": product.id,
            "forecast_qty": forecast_qty,
            "arrival_month": arrival_month,
            "expected_week": expected_week,
        }

        line = self.env["forecast.line"].create(line_vals)

        if apply_distribution:
            # Weekly distribution is auto-applied on create by the model
            # This is just documentation of expected behavior
            pass

        return line

    def create_allocation(
        self,
        plan,
        sale_order,
        product=None,
        plan_line=None,
        allocated_qty=10,
        is_non_forecast=False,
        state="confirmed",
    ):
        """
        Create a forecast allocation (manual).

        Args:
            plan (forecast.plan): Parent plan
            sale_order (sale.order): Linked sale order
            product (product.product): Product to allocate (default from plan_line)
            plan_line (forecast.line): Optional forecast line reference
            allocated_qty (float): Quantity to allocate
            is_non_forecast (bool): Mark as non-forecast sale
            state (str): Allocation state (draft, confirmed, cancel)

        Returns:
            forecast.allocation record
        """
        if plan_line is None and product is None:
            raise ValueError("Either plan_line or product must be provided")

        allocation_vals = {
            "plan_id": plan.id,
            "sale_order_id": sale_order.id,
            "allocated_qty": allocated_qty,
            "is_non_forecast": is_non_forecast,
            "state": state,
        }

        if plan_line:
            allocation_vals["plan_line_id"] = plan_line.id
            if product is None:
                allocation_vals["product_id"] = plan_line.product_id.id

        if product:
            allocation_vals["product_id"] = product.id

        return self.env["forecast.allocation"].create(allocation_vals)

    def create_sale_order(self, user=None, partner=None, lines=None, state="draft"):
        """
        Create a sale order with optional lines.

        Args:
            user (res.users): Salesperson (defaults to user_sales)
            partner (res.partner): Customer (defaults to partner_customer)
            lines (list): List of tuples (product, qty) or None for empty order
            state (str): Initial state (draft, sent, sale, done, cancel)

        Returns:
            sale.order record
        """
        from odoo import fields

        if user is None:
            user = self.user_sales
        if partner is None:
            partner = self.partner_customer

        order_vals = {
            "partner_id": partner.id,
            "user_id": user.id,
            "pricelist_id": self.pricelist.id,
            "state": state,
        }

        if state in ("sale", "done"):
            order_vals["date_order"] = fields.Datetime.now()

        order = self.env["sale.order"].create(order_vals)

        if lines:
            for product, qty in lines:
                self.env["sale.order.line"].create(
                    {
                        "order_id": order.id,
                        "product_id": product.id,
                        "product_uom_qty": qty,
                        "price_unit": product.lst_price,
                    }
                )

        return order

    def confirm_sale_order(self, sale_order):
        """
        Confirm a sale order, triggering auto-allocation.

        Args:
            sale_order (sale.order): Sale order to confirm

        Returns:
            sale.order record in 'sale' state
        """
        return sale_order.action_confirm()

    def get_current_month_start(self):
        """
        Get first day of current month.

        Returns:
            date
        """
        from odoo import fields
        return fields.Date.start_of(fields.Date.context_today(self), "month")

    def get_next_month_start(self, months=1):
        """
        Get first day of next month(s).

        Args:
            months (int): Number of months ahead

        Returns:
            date
        """
        from dateutil.relativedelta import relativedelta

        start = self.get_current_month_start()
        return start + relativedelta(months=months)


@tagged("post_install", "-at_install")
class ForecastSecurityTestCommon(ForecastTestCommon):
    """
    Extended common class for security testing with pre-authenticated user contexts.
    """

    def setUp(self):
        """
        Set up for each test: reset to base user.
        """
        super().setUp()
        # Reset to base user with no forecast groups
        self.env = self.env(user=self.user_planner)
